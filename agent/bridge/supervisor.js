// WhatsApp supervision agent.
//
// Rides the homeowner's own WhatsApp identity (whatsapp-web.js, linked-device
// session). Privacy model: WHITELIST-ONLY — the agent subscribes to exactly
// two chats and drops every other event at entry, unread and unstored:
//   1. the CONSOLE group — the household's decision group (homeowner + spouse/
//      family). Group membership IS the ACL: any member can feed floor plans
//      and approve drafts. Floor plans in, approvals in, results out.
//   2. the RENO group — the renovation group with contractors; read-only,
//      except messages explicitly approved by the human.
// Every outgoing message passes the human approval gate: live drafts are posted
// to the console as [#n] cards; only "ok n" typed by a human in WhatsApp
// releases them. The terminal command channel can dry-run test drafts only.
//
// Usage: node agent/bridge/supervisor.js      (group names in demo/config.json)
import pkg from 'whatsapp-web.js'
import QRCode from 'qrcode'
import fs from 'fs'
import path from 'path'
import readline from 'readline'
import { execFile } from 'child_process'
import { promisify } from 'util'
import { fileURLToPath } from 'url'
import { askClaude, parseJson } from '../llm.js'
import { auditRender } from '../factlayer/audit.js'
import { analyzeCatalog } from '../procurement/select.js'
import { buildReport } from '../ledger/report.js'
import { recordDecision, synthesizeSkill, countDecisions } from '../skills/skills.js'
import * as ledger from '../ledger/ledger.js'

const execFileP = promisify(execFile)

const { Client, LocalAuth, MessageMedia } = pkg
const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '../..')
const AUTH_PATH = process.env.WWEBJS_AUTH || path.join(ROOT, '../bridge-test/wwebjs_auth')
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

// singleton lock — two clients on one WhatsApp session detach each other's frames
const LOCK = path.join(ROOT, 'demo/supervisor.pid')
if (fs.existsSync(LOCK)) {
  const old = Number(fs.readFileSync(LOCK, 'utf8'))
  try { process.kill(old, 0); console.error(`another supervisor is running (pid ${old}) — exiting`); process.exit(1) } catch {}
}
fs.writeFileSync(LOCK, String(process.pid))
process.on('exit', () => { try { if (Number(fs.readFileSync(LOCK, 'utf8')) === process.pid) fs.unlinkSync(LOCK) } catch {} })

const cfg = JSON.parse(fs.readFileSync(path.join(ROOT, 'demo/config.json'), 'utf8'))
const RENO_GROUP = process.env.RENOAI_GROUP || cfg.reno_group
// multiple consoles supported: first entry is PRIMARY (approval drafts land there);
// replies to floor plans always go back to the group they were sent in
const CONSOLE_GROUPS = cfg.console_groups || [process.env.RENOAI_CONSOLE || cfg.console_group]

const log = (tag, msg) => console.log(`\x1b[36m[${new Date().toISOString().slice(11, 19)}]\x1b[0m \x1b[1m${tag}\x1b[0m ${msg}`)

const EXTRACT_SYSTEM = `You are the supervision module of RenoGent, monitoring a renovation WhatsApp group on behalf of the homeowner.
Today is ${new Date().toDateString()}. Given ONE incoming message, output pure JSON:
{
 "is_commitment": bool,
 "item": string|null,
 "promised_date": "YYYY-MM-DD"|null,
 "is_slippage_admission": bool,
 "is_work_proposal": bool,        // contractor proposes NEW renovation work / a scope change (hacking a wall, adding a recess, changing windows...)
 "proposed_work": string|null,    // the proposed work as one concise work item, e.g. "hack a recess into the household shelter wall for a fridge"
 "needs_reply": bool,
 "draft_reply": string|null
}
Resolve relative dates ("Friday","tmr") against today. Draft replies: firm but polite, cite specifics, English, <=60 words.
If is_work_proposal is true, do NOT draft an approval/rejection in draft_reply — compliance is checked separately; set needs_reply false unless something else needs answering.`

let client
let consoleChats = [] // approval + onboarding surfaces; [0] = primary
let renoChat = null // supervised renovation group
let pendingSeq = 0
const pending = new Map()
const AGENT_MARKS = ['🤖', '📒', '📐', '✅', '⚠️', '🔍', '🛠', '🎨', '📋', '🧠', '📍']

const isAgentPost = (body) => AGENT_MARKS.some((m) => (body || '').startsWith(m))

async function toConsole(text, mediaPath = null, chat = null) {
  // agent and homeowner share ONE WhatsApp account — every console message the
  // agent posts is 🤖-prefixed so the two voices can never be confused.
  // (Approved outbound messages to the reno group are the opposite, by design:
  // they speak AS the homeowner and carry no robot marker.)
  if (text && !text.startsWith('🤖')) text = `🤖 ${text}`
  const target = chat || consoleChats[0]
  if (!target) return console.log(`(console offline) ${text}`)
  for (let i = 0; i < 2; i++) {
    try {
      if (mediaPath) return await client.sendMessage(target.id._serialized, MessageMedia.fromFilePath(mediaPath), { caption: text })
      return await client.sendMessage(target.id._serialized, text)
    } catch (e) {
      log('ERR', `toConsole attempt ${i + 1} failed: ${e.message.slice(0, 120)}`)
      await new Promise((r) => setTimeout(r, 3000))
    }
  }
}
// claude playground console (for cmd-channel self-tests), falls back to primary
const claudeConsole = () => consoleChats.find((c) => /claude/i.test(c.name)) || consoleChats[0]
// homeowner's test console (render iteration) — NEVER the primary demo console
const testConsole = () => consoleChats.find((c) => /test/i.test(c.name) && !/claude/i.test(c.name)) || claudeConsole()

// origin 'live' → card to PRIMARY console, only a human in WhatsApp can release it
// origin 'test' → card to the claude playground console, cmd-channel ok = dry-run
async function propose(chatId, label, text, origin = 'live') {
  const n = ++pendingSeq
  pending.set(n, { chatId, text, label, origin })
  const target = origin === 'test' ? claudeConsole() : consoleChats[0]
  log('DRAFT', `[#${n}]${origin === 'test' ? ' [test]' : ''} → ${label}: ${text.slice(0, 100)}`)
  await toConsole(`🤖 DRAFT${origin === 'test' ? ' [test]' : ''} [#${n}] → ${label}\n────────────\n${text}\n────────────\nreply "ok ${n}" to send · "no ${n}" to discard`, null, target)
}

// via 'wa' = a human typed in WhatsApp (full authority)
// via 'cmd' = automation channel: may discard anything, may only DRY-RUN test drafts
async function decide(text, approver = 'homeowner', via = 'wa') {
  const m = (text || '').trim().match(/^(ok|yes|send|no|drop)\s*#?(\d+)/i)
  if (!m) return false
  const n = Number(m[2])
  const p = pending.get(n)
  if (!p) return false
  const confirmTo = p.origin === 'test' ? claudeConsole() : consoleChats[0]
  if (/^(no|drop)/i.test(m[1])) {
    pending.delete(n)
    log('GATE', `[#${n}] discarded by ${approver} (${via})`)
    await toConsole(`✅ [#${n}] discarded (by ${approver}).`, null, confirmTo)
    return true
  }
  if (via === 'cmd') {
    if (p.origin !== 'test') {
      log('GATE', `[#${n}] REFUSED: live draft, cmd channel cannot approve — human gate only`)
      return true
    }
    pending.delete(n)
    log('GATE', `[#${n}] [test] dry-run approved via cmd — NOT sent`)
    await toConsole(`✅ [dry-run] [#${n}] would send to ${p.label}:\n"${p.text}"\n(no real message sent — test drafts need a human "ok" in WhatsApp to actually send)`, null, confirmTo)
    return true
  }
  pending.delete(n)
  await client.sendMessage(p.chatId, p.text)
  log('SENT', `[#${n}] approved by ${approver} → ${p.label}`)
  await toConsole(`✅ [#${n}] sent to ${p.label} (approved by ${approver}).`, null, confirmTo)
  return true
}

// ---------- console: floor-plan onboarding ----------
// most recent floor-plan run: {file, style} — powers "redo <room>"; persisted so
// redo survives supervisor restarts (briefs are cached next to the plan file)
const LASTPLAN_FILE = path.join(ROOT, 'demo/lastplan.json')
let lastPlan = fs.existsSync(LASTPLAN_FILE) ? JSON.parse(fs.readFileSync(LASTPLAN_FILE, 'utf8')) : null
const setLastPlan = (p) => { lastPlan = p; fs.writeFileSync(LASTPLAN_FILE, JSON.stringify(p)) }

// shared whole-flat progress reporter; `say` is scoped to whichever chat asked
const renderProgressCb = (say) => async (stage, room, payload) => {
  if (stage === 'briefs') await say(`🔍 Analyzing the floor plan into per-room briefs (walls, windows, doors, camera) — about 1 minute…`)
  else if (stage === 'render') {
    log('ROOM', `rendering ${room.name}${payload?.retry_base ? ` (base ${payload.retry_base})` : ''}`)
    await say(payload?.retry_base
      ? `🎨 ${room.name}: previous base plateaued — fresh render #${payload.retry_base}, carrying every audit constraint…`
      : `🎨 Rendering ${room.name}…`)
  }
  else if (stage === 'fix')
    await say(`🛠 ${room.name}: audit caught ${payload.violations.length} violation(s):\n${payload.violations.map((v) => `• [${v.element}] ${v.evidence}`).join('\n')}\nApplying surgical re-edit…`)
  else if (stage === 'done') {
    const v = payload.audit?.violations || []
    const detail = v.map((x) => `• L${x.layer || '?'} [${x.element}] ${x.evidence}`).join('\n')
    if (payload.status === 'blocked') {
      // HARD RULE: structural violations → no image released, report only
      await say(`❌ ${room.name} — ${payload.attempts} attempt(s), NONE passed the structural audit (L1/L2). No render released — a structurally wrong image is worse than no image.\nClosest attempt failed on:\n${detail}\nReply *redo ${room.name}* for a fresh set of attempts.`)
      return
    }
    if (payload.cameraPlan)
      await say(`📍 ${room.name} — viewpoint for render #${payload.hash}: red dot = where you stand, arrow = where you look.\nFrom here you should see: ${room.visible_from_camera || room.camera}`, payload.cameraPlan)
    const verdict = payload.status === 'passed'
      ? `✅ PASSED (components, depth/scale and style match the plan) in ${payload.attempts} attempt(s)`
      : payload.audit
        ? `🟡 structure verified ✓ — ${v.length} STYLE issue(s) left for your judgement:\n${detail}\nReply *redo ${room.name}* if it's not to taste.`
        : 'skipped (audit errored)'
    await say(`📐 ${room.name} — render #${payload.hash || 'n/a'} · audit ${verdict}`, payload.file)
  }
  else if (stage === 'error') await say(`⚠️ ${room.name} render failed: ${String(payload).slice(0, 120)}`)
}

async function onboardImage(m, srcChat) {
  const media = await m.downloadMedia()
  if (!media) return
  const ext = (media.mimetype || 'image/jpeg').split('/')[1].split(';')[0]
  const inbox = path.join(ROOT, 'demo/inbox')
  fs.mkdirSync(inbox, { recursive: true })
  const file = path.join(inbox, `plan-${Date.now()}.${ext}`)
  fs.writeFileSync(file, Buffer.from(media.data, 'base64'))
  log('ONBOARD', `image received -> ${file} (caption: ${m.body || 'none'})`)

  // visible liveness: keep the WhatsApp "typing…" indicator on while working
  const typer = setInterval(() => { try { srcChat?.sendStateTyping() } catch {} }, 20000)
  try { srcChat?.sendStateTyping() } catch {}
  const stopTyping = () => { clearInterval(typer); try { srcChat?.clearState() } catch {} }
  // all replies for this onboarding go back to the group the image came from
  const say = (text, mediaPath = null) => toConsole(text, mediaPath, srcChat)

  const runRender = (src, dst, promptText) =>
    execFileP('python3', [path.join(ROOT, 'agent/factlayer/render.py'), src, dst, promptText], { timeout: 240000 })

  // ---- whole-flat path: floor plan → per-room briefs → constrained render+audit per room ----
  try {
    const { renderAllRooms } = await import('../factlayer/render_all.js')
    const style = m.body?.trim() || 'warm japandi style, matte oak flooring, warm cove lighting, linen curtains'
    await say(`📐 Received. Reading the plan into per-room briefs (fact layer), then rendering every room with your brief: "${style.slice(0, 120)}"…`)
    setLastPlan({ file, style })
    const res = await renderAllRooms(file, style, renderProgressCb(say))
    if (res.is_floor_plan) {
      const passed = res.results.filter((r) => r.status === 'passed').length
      const style = res.results.filter((r) => r.status === 'style-escalation').length
      const blocked = res.results.filter((r) => r.status === 'blocked').length
      const failed = res.results.filter((r) => r.error).length
      await say(`🏁 Whole-flat pass complete: ✅ ${passed} passed · 🟡 ${style} structure-verified with style questions for you · ❌ ${blocked} structurally blocked (no image released)${failed ? ` · ${failed} render errors` : ''}. Reply "redo <room>" to retry any room.`)
      const triagePath = path.join(ROOT, 'demo/triage-output.json')
      if (fs.existsSync(triagePath)) {
        const t = JSON.parse(fs.readFileSync(triagePath, 'utf8'))
        const icon = { green: '🟢', amber: '🟡', red: '🔴', escalate: '🟣' }
        await say(`⚠️ Compliance triage for your requested works (citations verbatim-verified against hdb.gov.sg):\n${t.map((r) => `${icon[r.classification]} ${r.id}: ${r.reasoning.split('.')[0]}.`).join('\n')}`)
      }
      stopTyping()
      return
    }
    // not a plan → fall through to single-photo flow below
  } catch (err) {
    log('ERR', `whole-flat path failed, falling back to single render: ${err.message.slice(0, 150)}`)
  }

  await say(`📐 Treating this as a room photo. Rendering with geometry pinned to your original, then auditing…`)
  try {
    // 1. structure-locked render (locked recipe, ~11s)
    let out = file.replace(/\.[a-z]+$/, '-render.png')
    const style = m.body?.trim() ? `Renovate this room: ${m.body.trim()}. Photorealistic, realistic materials.` : ''
    await runRender(file, out, style)

    // 2. audit hook: render vs original, element by element
    await say(`🔍 Auditing render against your original — windows, doors, walls, ceiling, beams & columns…`)
    let audit
    try { audit = await auditRender(file, out, m.body || '') } catch (e) { log('ERR', `audit failed: ${e.message}`); audit = null }

    // 3. violations -> surgical corrective re-edit -> re-audit
    if (audit && !audit.pass && audit.violations?.length) {
      const list = audit.violations.map((v) => `• [${v.element}] ${v.evidence}`).join('\n')
      await say(`🛠 Audit caught ${audit.violations.length} violation(s):\n${list}\nApplying surgical re-edit (only the offending elements)…`)
      log('AUDIT', `FAIL: ${audit.violations.map((v) => v.element).join(', ')}`)
      const fixes = audit.violations.map((v) => v.edit_instruction).join(' ')
      const fixed = out.replace('-render.png', '-render-fixed.png')
      await runRender(out, fixed, `${fixes} Change ONLY these elements; keep everything else pixel-identical.`)
      out = fixed
      try {
        const re = await auditRender(file, out, m.body || '')
        log('AUDIT', re.pass ? 'PASS after re-edit' : `still failing: ${re.violations?.map((v) => v.element).join(', ')}`)
        await say(re.pass
          ? `📐 Re-audit passed. ${re.room ? 'Room: ' + re.room + '. ' : ''}Corrected render:`
          : `📐 Re-audit: ${re.violations?.length || 0} issue(s) remain — escalating to you with the best version (${re.room || 'room unverified'}):`, out)
      } catch { await say(`📐 Corrected render (re-audit unavailable):`, out) }
    } else {
      log('AUDIT', audit ? 'PASS first try' : 'SKIPPED (audit error)')
      await say(`📐 Structure-locked render — audit ${audit ? `passed: geometry matches your original. Room: ${audit.room || 'n/a'}` : 'skipped'}:`, out)
    }

    // 4. compliance summary from the latest triage run
    const triagePath = path.join(ROOT, 'demo/triage-output.json')
    if (fs.existsSync(triagePath)) {
      const t = JSON.parse(fs.readFileSync(triagePath, 'utf8'))
      const icon = { green: '🟢', amber: '🟡', red: '🔴', escalate: '🟣' }
      const lines = t.map((r) => `${icon[r.classification]} ${r.id}: ${r.reasoning.split('.')[0]}.`).join('\n')
      await say(`⚠️ Compliance triage (every citation verbatim-verified against hdb.gov.sg):\n${lines}`)
    }
  } catch (err) {
    log('ERR', `onboard pipeline failed: ${err.message}`)
    await say(`⚠️ Pipeline error — image logged to fact layer, retry with another photo.`)
  } finally {
    stopTyping()
  }
}

// ---------- procurement: catalog → top-3 (Phase A) or learned auto-pick (Phase B) ----------
const REQ_FILE = path.join(ROOT, 'demo/skills/current-requirements.txt')
const getRequirements = () =>
  fs.existsSync(REQ_FILE) ? fs.readFileSync(REQ_FILE, 'utf8').trim() : 'oak color vinyl flooring, durable, reasonable budget'
let lastChoice = null // one open selection card at a time

async function handleCatalog(m, origin = 'live') {
  const media = await m.downloadMedia()
  if (!media) return
  const ext = (media.mimetype || 'application/pdf').split('/')[1].split(';')[0].replace('vnd.', '')
  const inbox = path.join(ROOT, 'demo/inbox')
  fs.mkdirSync(inbox, { recursive: true })
  const file = path.join(inbox, `catalog-${Date.now()}.${ext}`)
  fs.writeFileSync(file, Buffer.from(media.data, 'base64'))
  const requirements = m.body?.trim() || getRequirements()
  const say = (t, mp = null) => toConsole(t, mp, origin === 'test' ? claudeConsole() : consoleChats[0])
  await say(`📋 Catalog received (${ext}). Analyzing every option against your requirements: "${requirements}"…`)
  log('CATALOG', `${file} req="${requirements}" origin=${origin}`)
  try {
    // test-channel decisions live under a namespaced domain so playground picks
    // never contaminate the household's real decision profile — the prefix must
    // reach analyzeCatalog BEFORE its skill lookup, or auto mode can't trigger
    const res = await analyzeCatalog({ filePath: path.resolve(file), requirements, domainPrefix: origin === 'test' ? 'test-' : '' })
    log('CATALOG', `mode=${res.mode} domain=${res.domain} (${countDecisions(res.domain)} decision(s) on file)`)
    if (res.mode === 'auto') {
      recordDecision(res.domain, { mode: 'auto', requirements, pick: res.pick.name, applied_rules: res.applied_rules })
      await say(
        `🧠 Applied your learned decision profile (${countDecisions(res.domain)} past decision(s), domain: ${res.domain}) — selected:\n` +
        `*${res.pick.name}* — ${res.pick.price} · ${res.pick.material} · ${res.pick.color} · ${res.pick.durability}\n` +
        `Why: ${res.pick.rationale}\nRules applied: ${(res.applied_rules || []).join('; ')}\n` +
        `Runner-up: ${res.runner_up?.name || 'n/a'} (${res.runner_up?.why_not || ''})`
      )
      if (renoChat) await propose(renoChat.id._serialized, `${renoChat.name} (selection)`, `Hi, we've decided on ${res.pick.name}. Please confirm availability, final price and lead time.`, origin)
    } else {
      lastChoice = { domain: res.domain, options: res.options, requirements, origin }
      const card = res.options
        .map((o) => `*${o.label}. ${o.name}* — ${o.price} · ${o.material} · ${o.color} · ${o.durability}\n   ✓ ${(o.pros || []).join(' / ')}\n   ✗ ${(o.cons || []).join(' / ')}`)
        .join('\n\n')
      await say(`📋 Top 3 for "${requirements}":\n\n${card}\n\n(rest excluded: ${res.excluded_because || 'weaker fit'})\n\nReply *A*, *B* or *C* — add a word on why, I learn your priorities from it.`)
    }
  } catch (e) {
    log('ERR', `catalog analysis failed: ${e.message.slice(0, 150)}`)
    await say(`⚠️ Catalog analysis failed — file logged, will retry on resend.`)
  }
}

async function handleChoicePick(text, who, origin) {
  const m = (text || '').trim().match(/^([abc])\b[\s,.:;-]*(.*)$/i)
  if (!m || !lastChoice) return false
  const choice = lastChoice
  lastChoice = null
  const picked = choice.options.find((o) => o.label.toUpperCase() === m[1].toUpperCase())
  if (!picked) return false
  const say = (t) => toConsole(t, null, choice.origin === 'test' ? claudeConsole() : consoleChats[0])
  recordDecision(choice.domain, {
    mode: 'human-pick', requirements: choice.requirements,
    options: choice.options.map((o) => ({ label: o.label, name: o.name, price: o.price, durability: o.durability })),
    chose: picked.name, reason: m[2] || '(none stated)', by: who,
  })
  await say(`✅ Noted: *${picked.name}* (picked by ${who}${m[2] ? `, reason: "${m[2]}"` : ''}). Distilling your decision profile…`)
  try {
    const md = await synthesizeSkill(choice.domain)
    await say(`🧠 Decision profile updated — ${countDecisions(choice.domain)} decision(s) in *${choice.domain}*:\n${md.slice(0, 500)}…\n\nNext ${choice.domain.replace('test-', '')} catalog: I pick directly, you just confirm.`)
  } catch (e) { log('ERR', `skill synthesis failed: ${e.message.slice(0, 120)}`) }
  if (renoChat) await propose(renoChat.id._serialized, `${renoChat.name} (selection)`, `Hi, we'll go with ${picked.name}. Please confirm availability, final price and lead time.`, choice.origin)
  return true
}

async function onConsoleMessage(m, srcChat) {
  if (isAgentPost(m.body)) return
  const who = m.fromMe ? client.info.pushname : m._data?.notifyName || 'family member'
  const origin = /claude/i.test(srcChat?.name || '') ? 'test' : 'live' // claude group = playground
  if (m.hasMedia) {
    if (m.type === 'document') return handleCatalog(m, origin)
    return onboardImage(m, srcChat)
  }
  // PM layer: progress/budget report + budget cap + per-room redo
  if (/^report$/i.test(m.body?.trim() || '')) return toConsole(buildReport(), null, srcChat)
  const bud = m.body?.match(/^budget\s+\$?([\d,]+)/i)
  if (bud) {
    const total = Number(bud[1].replace(/,/g, ''))
    const bp = path.join(ROOT, 'demo/budget.json')
    const b = fs.existsSync(bp) ? JSON.parse(fs.readFileSync(bp, 'utf8')) : { committed: [] }
    b.total = total
    fs.writeFileSync(bp, JSON.stringify(b, null, 2))
    return toConsole(`✅ Budget cap set to S$${total.toLocaleString('en-SG')} — parsed quotes fill the committed lines. Reply *report* for the full picture.`, null, srcChat)
  }
  const redo = m.body?.match(/^redo\s+(.+)/i)
  if (redo && lastPlan) {
    const say = (t, mp = null) => toConsole(t, mp, srcChat)
    await say(`🎨 Redo ${redo[1].trim()} — fresh base render, reusing the plan's cached briefs…`)
    const { renderAllRooms } = await import('../factlayer/render_all.js')
    renderAllRooms(lastPlan.file, lastPlan.style, renderProgressCb(say), redo[1].trim())
      .catch((e) => say(`⚠️ redo failed: ${String(e.message).slice(0, 120)}`))
    return
  }
  const req = m.body?.match(/^req(?:uirements)?\s*[:：]\s*(.+)/i)
  if (req) {
    fs.mkdirSync(path.dirname(REQ_FILE), { recursive: true })
    fs.writeFileSync(REQ_FILE, req[1].trim())
    return toConsole(`✅ Requirements saved: "${req[1].trim()}" — applied to the next catalog.`, null, srcChat)
  }
  if (await handleChoicePick(m.body, who, origin)) return
  if (await decide(m.body, who, 'wa')) return
  // anything else in the console is ignored by design (privacy: no parsing, no storage)
}

// ---------- reno group: supervision ----------
async function onRenoMessage(m, origin = 'live') {
  const sender = m._data?.notifyName || m.author || 'contractor'
  log('MSG-IN', `${sender}: ${m.body || `[${m.type}]`}`)
  // proactive: contractor drops a catalog/quote document → analyze without being asked
  if (m.hasMedia && m.type === 'document') return handleCatalog(m, origin)
  let x
  try {
    x = parseJson(await askClaude(`Message from "${sender}":\n"""${m.body}"""`, { system: EXTRACT_SYSTEM, maxTokens: 600 }))
  } catch (e) { log('ERR', `extraction failed: ${e.message}`); return }

  if (x.is_commitment && x.item) {
    const entry = ledger.append({ who: sender, item: x.item, promised_date: x.promised_date, source_msg: m.body, chat: renoChat?.name, ts: new Date().toISOString() })
    log('LEDGER', `${entry.id}: "${entry.item}" by ${entry.promised_date || 'unspecified'} (${sender})`)
    await toConsole(`📒 Logged ${entry.id}: "${entry.item}" — promised ${entry.promised_date || 'no date'} by ${sender}`, null, origin === 'test' ? claudeConsole() : null)
  }
  if (x.needs_reply && x.draft_reply) await propose(renoChat.id._serialized, renoChat.name, x.draft_reply, origin)

  // contractor proposes new work → live compliance triage with verbatim citations
  if (x.is_work_proposal && x.proposed_work) {
    const con = origin === 'test' ? claudeConsole() : null
    await toConsole(`🔍 ${sender} proposes: "${x.proposed_work}" — checking against HDB rules (citations machine-verified)…`, null, con)
    try {
      const { triage } = await import('../compliance/triage.js')
      const [t] = await triage([{ id: 'LIVE-1', item: x.proposed_work }])
      const icon = { green: '🟢', amber: '🟡', red: '🔴', escalate: '🟣' }[t.classification] || '🟣'
      const cites = (t.citations || []).filter((c) => c.verified).map((c) => `"${c.quote}"\n  — ${c.source_url}`).join('\n')
      await toConsole(`${icon} ${t.classification.toUpperCase()}: ${x.proposed_work}\n${t.reasoning}${cites ? `\n\nVerified citations:\n${cites}` : ''}`, null, con)
      if (t.classification === 'red' || t.classification === 'amber') {
        const q = (t.citations || []).find((c) => c.verified)
        const reply = t.classification === 'red'
          ? `Thanks for the suggestion, but we'll skip the ${x.proposed_work.replace(/\.$/, '')} — HDB rules don't allow it${q ? ` ("${q.quote.slice(0, 120)}…", hdb.gov.sg)` : ''}. Let's keep to the approved scope.`
          : `On the ${x.proposed_work.replace(/\.$/, '')} — it's possible but conditional: ${t.reasoning.slice(0, 160)}. Let's confirm the permit/conditions before any work starts.`
        await propose(renoChat.id._serialized, `${renoChat.name} (compliance)`, reply, origin)
      }
    } catch (e) { log('ERR', `live triage failed: ${e.message.slice(0, 120)}`) }
  }
}

async function chaseSlippage() {
  if (!renoChat) return
  for (const s of ledger.slipped().slice(0, 3)) {
    const draft = await askClaude(
      `Commitment ${s.id}: "${s.item}" was promised for ${s.promised_date} by ${s.who} (their words: "${s.source_msg}"). It is now overdue. Draft a firm but polite WhatsApp chase message from the homeowner citing the original promise and date, asking for a concrete new completion date. Address them directly as "${s.who}" — NO placeholders or square brackets. <=50 words, message text only.`,
      { maxTokens: 300 }
    )
    await propose(renoChat.id._serialized, `${renoChat.name} (chase ${s.id})`, draft.trim())
  }
}

// ---------- wiring ----------
client = new Client({
  authStrategy: new LocalAuth({ dataPath: AUTH_PATH }),
  puppeteer: { headless: true, executablePath: fs.existsSync(CHROME) ? CHROME : undefined, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
})

client.on('qr', async (qr) => { await QRCode.toFile('./qr.png', qr, { width: 400 }); log('QR', 'scan ./qr.png') })

client.on('disconnected', async (reason) => {
  log('DISC', `disconnected: ${reason} — reinitializing in 10s`)
  await new Promise((r) => setTimeout(r, 10000))
  try { await client.initialize() } catch (e) { log('ERR', `reinit failed: ${e.message.slice(0, 120)}`) }
})

client.on('ready', async () => {
  log('READY', `riding ${client.info.pushname} (${client.info.wid.user})`)
  const chats = await client.getChats()
  const findGroup = (name) => chats.find((c) => c.isGroup && c.name.toLowerCase().includes(name.toLowerCase()))
  consoleChats = CONSOLE_GROUPS.map(findGroup).filter(Boolean)
  renoChat = findGroup(RENO_GROUP)
  consoleChats.forEach((c, i) => log('WIRE', `console[${i}]${i === 0 ? ' (primary/human gate)' : ''}: "${c.name}"`))
  if (!consoleChats.length) log('WIRE', `console: NOT FOUND — create a group matching one of: ${CONSOLE_GROUPS.join(', ')}`)
  log('WIRE', `reno group: ${renoChat ? '"' + renoChat.name + '"' : 'NOT FOUND — create a group named "' + RENO_GROUP + '"'}`)
  log('WIRE', `whitelist active: all other chats are dropped at entry`)
  if (consoleChats[0]) await toConsole(`🤖 RenoGent online. Send a floor plan (caption = your style brief) for a whole-flat per-room render, or a room photo for a single render. Contractor promises in "${renoChat?.name || RENO_GROUP}" are logged; overdue ones produce chase drafts needing your "ok".`)
  await chaseSlippage()

  const route = async (m) => {
    const chatId = (m.fromMe ? m.to : m.from) || ''
    const console_ = consoleChats.find((c) => chatId === c.id._serialized)
    if (console_) {
      // console = household decision group: every member (homeowner, spouse,
      // family) can feed plans and approve drafts — membership is the ACL
      return onConsoleMessage(m, console_)
    }
    if (renoChat && chatId === renoChat.id._serialized) {
      if (!m.fromMe) return onRenoMessage(m, 'live')
      return
    }
    // whitelist: every other chat is dropped here — not read, not stored
  }
  client.on('message', route)
  client.on('message_create', (m) => { if (m.fromMe) route(m) })

  // PM layer: weekly digest every Monday 9am (checked hourly), plus on-demand "report"
  let lastWeekly = null
  setInterval(() => {
    const now = new Date()
    const stamp = now.toISOString().slice(0, 10)
    if (now.getDay() === 1 && now.getHours() >= 9 && lastWeekly !== stamp && consoleChats[0]) {
      lastWeekly = stamp
      toConsole(buildReport(), null, consoleChats[0]).catch(() => {})
    }
  }, 3600 * 1000)
})

// a single failed puppeteer call must never take the supervisor down
process.on('unhandledRejection', (e) => log('ERR', `unhandled: ${String(e?.message || e).slice(0, 200)}`))
process.on('uncaughtException', (e) => log('ERR', `uncaught: ${String(e?.message || e).slice(0, 200)}`))

// ---------- local test-command channel ----------
// Commands via stdin OR appended to demo/cmd.txt (for driving a detached process):
//   img <path> [caption]  -> post an image into the console group as the homeowner
//   post <path> [caption] -> post an already-generated image to the test console as the agent
//   say <text>            -> post text into the console group as the homeowner
//   sim <text>            -> simulate an incoming contractor message (no WhatsApp
//                            message is sent anywhere; extraction+ledger+draft only)
//   ok N / no N           -> decide directly
async function handleCommand(line) {
  const t = line.trim()
  if (!t) return
  const [cmd, ...rest] = t.split(' ')
  try {
    const playground = claudeConsole() // cmd channel only ever touches the claude console
    if (cmd === 'img' && playground) {
      await client.sendMessage(playground.id._serialized, MessageMedia.fromFilePath(rest[0]), { caption: rest.slice(1).join(' ') })
      log('CMD', `img posted to "${playground.name}": ${rest[0]}`)
    } else if (cmd === 'post') {
      const target = testConsole()
      await toConsole(rest.slice(1).join(' ') || `Manual render candidate: ${path.basename(rest[0])}`, rest[0], target)
      log('CMD', `post sent to "${target?.name}": ${rest[0]}`)
    } else if (cmd === 'say' && playground) {
      await client.sendMessage(playground.id._serialized, rest.join(' '))
      log('CMD', `say posted to "${playground.name}": ${rest.join(' ')}`)
    } else if (cmd === 'doc' && playground) {
      await client.sendMessage(playground.id._serialized, MessageMedia.fromFilePath(rest[0]), { caption: rest.slice(1).join(' '), sendMediaAsDocument: true })
      log('CMD', `doc posted to "${playground.name}": ${rest[0]}`)
    } else if (cmd === 'rerun') {
      // homeowner-requested: re-run the whole flat (or one room) from the cached
      // plan, reporting to the PRIMARY console. Only console status posts — the
      // human send-gate for outbound messages is untouched.
      if (!lastPlan) { log('CMD', 'rerun refused: no cached plan'); return }
      const target = testConsole() // render iteration lives in the TEST console — the demo console stays clean
      const say2 = (t, mp = null) => toConsole(t, mp, target)
      const roomFilter = rest.join(' ').trim() || null
      log('CMD', `rerun ${roomFilter || 'whole flat'} from ${lastPlan.file}`)
      await say2(`🎨 Re-running ${roomFilter || 'every room'} under the new structural gate (L1/L2 violations = no image released). Briefs are cached — first render starts now.`)
      const { renderAllRooms } = await import('../factlayer/render_all.js')
      renderAllRooms(lastPlan.file, lastPlan.style, renderProgressCb(say2), roomFilter)
        .then(async (res) => {
          const passed = res.results.filter((r) => r.status === 'passed').length
          const styleQ = res.results.filter((r) => r.status === 'style-escalation').length
          const blocked = res.results.filter((r) => r.status === 'blocked').length
          await say2(`🏁 Re-run complete: ✅ ${passed} passed · 🟡 ${styleQ} structure-verified with style questions · ❌ ${blocked} blocked (no image). "redo <room>" to retry any.`)
        })
        .catch((e) => say2(`⚠️ rerun failed: ${String(e.message).slice(0, 140)}`))
    } else if (cmd === 'pick' && lastChoice) {
      if (lastChoice.origin !== 'test') { log('CMD', 'REFUSED: live selection card, human gate only'); return }
      await handleChoicePick(rest.join(' '), 'claude-cmd', 'test')
    } else if (cmd === 'sim') {
      log('CMD', `simulating contractor message: ${rest.join(' ')}`)
      await onRenoMessage({ body: rest.join(' '), _data: { notifyName: 'Contractor T' } }, 'test')
    } else {
      await decide(t, 'claude-cmd', 'cmd')
    }
  } catch (e) { log('ERR', `cmd failed: ${e.message.slice(0, 150)}`) }
}

const CMD_FILE = path.join(ROOT, 'demo/cmd.txt')
let cmdOffset = fs.existsSync(CMD_FILE) ? fs.statSync(CMD_FILE).size : 0
setInterval(() => {
  if (!fs.existsSync(CMD_FILE)) return
  const size = fs.statSync(CMD_FILE).size
  if (size <= cmdOffset) { cmdOffset = size; return }
  const fd = fs.openSync(CMD_FILE, 'r')
  const buf = Buffer.alloc(size - cmdOffset)
  fs.readSync(fd, buf, 0, buf.length, cmdOffset)
  fs.closeSync(fd)
  cmdOffset = size
  buf.toString('utf8').split('\n').forEach((l) => l.trim() && handleCommand(l))
}, 2000)

const rl = readline.createInterface({ input: process.stdin })
rl.on('line', handleCommand)

log('INIT', `auth=${AUTH_PATH} consoles=${JSON.stringify(CONSOLE_GROUPS)} reno="${RENO_GROUP}"`)
client.initialize()
