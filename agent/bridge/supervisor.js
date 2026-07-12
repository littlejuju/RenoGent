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
// Every outgoing message passes the human approval gate: drafts are posted to
// the console as [#n] cards; only "ok n" (console or terminal) releases them.
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
import * as ledger from '../ledger/ledger.js'

const execFileP = promisify(execFile)

const { Client, LocalAuth, MessageMedia } = pkg
const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '../..')
const AUTH_PATH = process.env.WWEBJS_AUTH || path.join(ROOT, '../bridge-test/wwebjs_auth')
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const cfg = JSON.parse(fs.readFileSync(path.join(ROOT, 'demo/config.json'), 'utf8'))
const RENO_GROUP = process.env.RENOAI_GROUP || cfg.reno_group
const CONSOLE_GROUP = process.env.RENOAI_CONSOLE || cfg.console_group

const log = (tag, msg) => console.log(`\x1b[36m[${new Date().toISOString().slice(11, 19)}]\x1b[0m \x1b[1m${tag}\x1b[0m ${msg}`)

const EXTRACT_SYSTEM = `You are the supervision module of RenoAI, monitoring a renovation WhatsApp group on behalf of the homeowner.
Today is ${new Date().toDateString()}. Given ONE incoming message, output pure JSON:
{
 "is_commitment": bool,
 "item": string|null,
 "promised_date": "YYYY-MM-DD"|null,
 "is_slippage_admission": bool,
 "needs_reply": bool,
 "draft_reply": string|null
}
Resolve relative dates ("Friday","tmr") against today. Draft replies: firm but polite, cite specifics, English, <=60 words.`

let client
let consoleChat = null // approval + onboarding surface
let renoChat = null // supervised renovation group
let pendingSeq = 0
const pending = new Map()
const AGENT_MARKS = ['🤖', '📒', '📐', '✅', '⚠️', '🔍', '🛠']

const isAgentPost = (body) => AGENT_MARKS.some((m) => (body || '').startsWith(m))

async function toConsole(text, mediaPath = null) {
  if (!consoleChat) return console.log(`(console offline) ${text}`)
  if (mediaPath) return client.sendMessage(consoleChat.id._serialized, MessageMedia.fromFilePath(mediaPath), { caption: text })
  return client.sendMessage(consoleChat.id._serialized, text)
}

async function propose(chatId, label, text) {
  const n = ++pendingSeq
  pending.set(n, { chatId, text, label })
  log('DRAFT', `[#${n}] → ${label}: ${text.slice(0, 100)}`)
  await toConsole(`🤖 DRAFT [#${n}] → ${label}\n────────────\n${text}\n────────────\nreply "ok ${n}" to send · "no ${n}" to discard`)
}

async function decide(text, approver = 'homeowner') {
  const m = (text || '').trim().match(/^(ok|yes|send|no|drop)\s*#?(\d+)/i)
  if (!m) return false
  const p = pending.get(Number(m[2]))
  if (!p) return false
  pending.delete(Number(m[2]))
  if (/^(no|drop)/i.test(m[1])) {
    log('GATE', `[#${m[2]}] discarded by ${approver}`)
    await toConsole(`✅ [#${m[2]}] discarded (by ${approver}).`)
  } else {
    await client.sendMessage(p.chatId, p.text)
    log('SENT', `[#${m[2]}] approved by ${approver} → ${p.label}`)
    await toConsole(`✅ [#${m[2]}] sent to ${p.label} (approved by ${approver}).`)
  }
  return true
}

// ---------- console: floor-plan onboarding ----------
async function onboardImage(m) {
  const media = await m.downloadMedia()
  if (!media) return
  const ext = (media.mimetype || 'image/jpeg').split('/')[1].split(';')[0]
  const inbox = path.join(ROOT, 'demo/inbox')
  fs.mkdirSync(inbox, { recursive: true })
  const file = path.join(inbox, `plan-${Date.now()}.${ext}`)
  fs.writeFileSync(file, Buffer.from(media.data, 'base64'))
  log('ONBOARD', `image received -> ${file} (caption: ${m.body || 'none'})`)
  await toConsole(`📐 Received. Rendering with geometry pinned to your original, then auditing against the fact layer…`)

  const runRender = (src, dst, promptText) =>
    execFileP('python3', [path.join(ROOT, 'agent/factlayer/render.py'), src, dst, promptText], { timeout: 120000 })

  try {
    // 1. structure-locked render (locked recipe, ~11s)
    let out = file.replace(/\.[a-z]+$/, '-render.png')
    const style = m.body?.trim() ? `Renovate this room: ${m.body.trim()}. Photorealistic, realistic materials.` : ''
    await runRender(file, out, style)

    // 2. audit hook: render vs original, element by element
    await toConsole(`🔍 Auditing render against your original — windows, doors, walls, ceiling, beams & columns…`)
    let audit
    try { audit = await auditRender(file, out, m.body || '') } catch (e) { log('ERR', `audit failed: ${e.message}`); audit = null }

    // 3. violations -> surgical corrective re-edit -> re-audit
    if (audit && !audit.pass && audit.violations?.length) {
      const list = audit.violations.map((v) => `• [${v.element}] ${v.evidence}`).join('\n')
      await toConsole(`🛠 Audit caught ${audit.violations.length} violation(s):\n${list}\nApplying surgical re-edit (only the offending elements)…`)
      log('AUDIT', `FAIL: ${audit.violations.map((v) => v.element).join(', ')}`)
      const fixes = audit.violations.map((v) => v.edit_instruction).join(' ')
      const fixed = out.replace('-render.png', '-render-fixed.png')
      await runRender(out, fixed, `${fixes} Change ONLY these elements; keep everything else pixel-identical.`)
      out = fixed
      try {
        const re = await auditRender(file, out, m.body || '')
        log('AUDIT', re.pass ? 'PASS after re-edit' : `still failing: ${re.violations?.map((v) => v.element).join(', ')}`)
        await toConsole(re.pass
          ? `📐 Re-audit passed. ${re.room ? 'Room: ' + re.room + '. ' : ''}Corrected render:`
          : `📐 Re-audit: ${re.violations?.length || 0} issue(s) remain — escalating to you with the best version (${re.room || 'room unverified'}):`, out)
      } catch { await toConsole(`📐 Corrected render (re-audit unavailable):`, out) }
    } else {
      log('AUDIT', audit ? 'PASS first try' : 'SKIPPED (audit error)')
      await toConsole(`📐 Structure-locked render — audit ${audit ? `passed: geometry matches your original. Room: ${audit.room || 'n/a'}` : 'skipped'}:`, out)
    }

    // 4. compliance summary from the latest triage run
    const triagePath = path.join(ROOT, 'demo/triage-output.json')
    if (fs.existsSync(triagePath)) {
      const t = JSON.parse(fs.readFileSync(triagePath, 'utf8'))
      const icon = { green: '🟢', amber: '🟡', red: '🔴', escalate: '🟣' }
      const lines = t.map((r) => `${icon[r.classification]} ${r.id}: ${r.reasoning.split('.')[0]}.`).join('\n')
      await toConsole(`⚠️ Compliance triage (every citation verbatim-verified against hdb.gov.sg):\n${lines}`)
    }
  } catch (err) {
    log('ERR', `onboard pipeline failed: ${err.message}`)
    await toConsole(`⚠️ Pipeline error — image logged to fact layer, retry with another photo.`)
  }
}

async function onConsoleMessage(m) {
  if (isAgentPost(m.body)) return
  const who = m.fromMe ? client.info.pushname : m._data?.notifyName || 'family member'
  if (m.hasMedia) return onboardImage(m)
  if (await decide(m.body, who)) return
  // anything else in the console is ignored by design (privacy: no parsing, no storage)
}

// ---------- reno group: supervision ----------
async function onRenoMessage(m) {
  const sender = m._data?.notifyName || m.author || 'contractor'
  log('MSG-IN', `${sender}: ${m.body}`)
  let x
  try {
    x = parseJson(await askClaude(`Message from "${sender}":\n"""${m.body}"""`, { system: EXTRACT_SYSTEM, maxTokens: 600 }))
  } catch (e) { log('ERR', `extraction failed: ${e.message}`); return }

  if (x.is_commitment && x.item) {
    const entry = ledger.append({ who: sender, item: x.item, promised_date: x.promised_date, source_msg: m.body, chat: renoChat?.name, ts: new Date().toISOString() })
    log('LEDGER', `${entry.id}: "${entry.item}" by ${entry.promised_date || 'unspecified'} (${sender})`)
    await toConsole(`📒 Logged ${entry.id}: "${entry.item}" — promised ${entry.promised_date || 'no date'} by ${sender}`)
  }
  if (x.needs_reply && x.draft_reply) await propose(renoChat.id._serialized, renoChat.name, x.draft_reply)
}

async function chaseSlippage() {
  if (!renoChat) return
  for (const s of ledger.slipped().slice(0, 3)) {
    const draft = await askClaude(
      `Commitment ${s.id}: "${s.item}" was promised for ${s.promised_date} by ${s.who} (their words: "${s.source_msg}"). It is now overdue. Draft a firm but polite WhatsApp chase message from the homeowner citing the original promise and date, asking for a concrete new completion date. <=50 words, message text only.`,
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

client.on('ready', async () => {
  log('READY', `riding ${client.info.pushname} (${client.info.wid.user})`)
  const chats = await client.getChats()
  const findGroup = (name) => chats.find((c) => c.isGroup && c.name.toLowerCase().includes(name.toLowerCase()))
  consoleChat = findGroup(CONSOLE_GROUP)
  renoChat = findGroup(RENO_GROUP)
  log('WIRE', `console: ${consoleChat ? '"' + consoleChat.name + '"' : 'NOT FOUND — create a group named "' + CONSOLE_GROUP + '"'}`)
  log('WIRE', `reno group: ${renoChat ? '"' + renoChat.name + '"' : 'NOT FOUND — create a group named "' + RENO_GROUP + '"'}`)
  log('WIRE', `whitelist active: all other chats are dropped at entry`)
  if (consoleChat) await toConsole(`🤖 RenoAI online. Send a floor plan / room photo (with a style caption) to start. Contractor promises in "${renoChat?.name || RENO_GROUP}" are logged automatically; overdue ones produce chase drafts for your approval.`)
  await chaseSlippage()

  const route = async (m) => {
    const chatId = (m.fromMe ? m.to : m.from) || ''
    if (consoleChat && chatId === consoleChat.id._serialized) {
      // console = household decision group: every member (homeowner, spouse,
      // family) can feed plans and approve drafts — membership is the ACL
      return onConsoleMessage(m)
    }
    if (renoChat && chatId === renoChat.id._serialized) {
      if (!m.fromMe) return onRenoMessage(m)
      return
    }
    // whitelist: every other chat is dropped here — not read, not stored
  }
  client.on('message', route)
  client.on('message_create', (m) => { if (m.fromMe) route(m) })
})

const rl = readline.createInterface({ input: process.stdin })
rl.on('line', async (line) => { await decide(line) })

log('INIT', `auth=${AUTH_PATH} console="${CONSOLE_GROUP}" reno="${RENO_GROUP}"`)
client.initialize()
