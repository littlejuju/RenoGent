// Progress + budget report — the PM layer over the commitment ledger.
// One WhatsApp-formatted digest: what's done, what's due, what slipped (the
// blockers), and budget committed vs. cap. On-demand via "report" in the
// console, and scheduled weekly by the supervisor.
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import * as ledger from './ledger.js'

const BUDGET_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../demo/budget.json')

// trade-matched acceptance checklists: when a commitment closes, the report
// tells the homeowner HOW to verify the work before releasing payment
const ACCEPTANCE = [
  [/vinyl|flooring|spc|laminate/i, 'walk the full floor barefoot for lippage; tap random spots — no hollow sound; joint gaps <0.5mm; expansion gap at walls hidden by beading; no adhesive stains'],
  [/paint/i, 'check walls against daylight at a low angle for roller marks and patchiness; edges/corners cut clean; no drips on skirting or switches; agreed colour code on the can'],
  [/tile|tiling/i, 'tap every tile — hollow-sounding ones must be relaid; grout lines even; falls toward floor traps (pour a bottle of water and watch it drain); no lippage at corners'],
  [/electrical|wiring|lighting|point/i, 'test every switch and socket with a phone charger; lights on/off from each gang; LB cover labelled; ask for the licensed electrician sign-off'],
  [/plumb|tap|sink|toilet|basin/i, 'run every tap 2 minutes and check under-sink joints for weeping; flush twice; check floor trap drainage; water heater on and off'],
  [/carpentr|cabinet|wardrobe|vanity/i, 'open every door and drawer twice — soft-close works, no rubbing; internal laminate finished; alignment gaps even; no exposed chipboard'],
  [/aircon|trunking/i, 'run cooling 20 minutes — check trunking joints for condensation; drainage pipe gradient; remote modes all work'],
]
const acceptanceFor = (item) => ACCEPTANCE.find(([re]) => re.test(item))?.[1] || null

const fmt = (n) => 'S$' + Number(n).toLocaleString('en-SG')
const bar = (frac, width = 10) => {
  const filled = Math.min(width, Math.round(frac * width))
  return '▓'.repeat(filled) + '░'.repeat(Math.max(0, width - filled))
}

export function buildReport(today = new Date()) {
  const entries = ledger.load()
  const day = (d) => new Date(d + 'T23:59:59')
  const soonCutoff = new Date(today.getTime() + 7 * 864e5)

  const done = entries.filter((e) => e.status === 'done')
  const open = entries.filter((e) => e.status === 'open')
  const slipped = open.filter((e) => e.promised_date && day(e.promised_date) < today)
  const dueSoon = open.filter((e) => e.promised_date && day(e.promised_date) >= today && day(e.promised_date) <= soonCutoff)
  const later = open.filter((e) => !slipped.includes(e) && !dueSoon.includes(e))

  const lines = [`📊 *Renovation status — ${today.toISOString().slice(0, 10)}*`, '']

  // progress
  const total = entries.length
  lines.push(`*Progress* ${done.length}/${total} commitments closed  ${bar(total ? done.length / total : 0)}`)
  if (slipped.length) {
    lines.push('', `🔴 *Blockers — ${slipped.length} slipped promise(s):*`)
    for (const e of slipped) {
      const days = Math.floor((today - day(e.promised_date)) / 864e5) + 1
      lines.push(`  ${e.id} ${e.item} — ${e.who}, ${days}d overdue (promised ${e.promised_date})`)
    }
  } else {
    lines.push('', '🟢 No blockers — every open promise is still inside its date.')
  }
  if (dueSoon.length) {
    lines.push('', `🔜 *Due in the next 7 days:*`)
    for (const e of dueSoon) lines.push(`  ${e.id} ${e.item} — ${e.who}, due ${e.promised_date}`)
  }
  if (later.length) lines.push('', `⏳ ${later.length} more open item(s) with later/no dates.`)

  // acceptance: anything closed in the last 7 days gets a how-to-verify checklist
  const justDone = done.filter((e) => e.resolved_at && (today - new Date(e.resolved_at)) < 7 * 864e5)
  if (justDone.length) {
    lines.push('', `🔍 *Completed this week — verify before you pay:*`)
    for (const e of justDone) {
      lines.push(`  ${e.id} ${e.item} (${e.who})`)
      const a = acceptanceFor(e.item)
      if (a) lines.push(`    ✓ acceptance: ${a}`)
    }
  }

  // budget
  if (fs.existsSync(BUDGET_PATH)) {
    const b = JSON.parse(fs.readFileSync(BUDGET_PATH, 'utf8'))
    const committed = (b.committed || []).reduce((s, x) => s + x.amount, 0)
    const paid = (b.committed || []).filter((x) => x.paid).reduce((s, x) => s + x.amount, 0)
    const frac = b.total ? committed / b.total : 0
    lines.push('', `*Budget* ${fmt(committed)} committed of ${fmt(b.total)} cap  ${bar(frac)} ${(frac * 100).toFixed(0)}%`)
    lines.push(`  paid out ${fmt(paid)} · uncommitted headroom ${fmt(Math.max(0, b.total - committed))}`)
    if (committed > b.total) lines.push(`  🚨 OVER BUDGET by ${fmt(committed - b.total)} — largest recent additions:`)
    const top = [...(b.committed || [])].sort((x, y) => y.amount - x.amount).slice(0, 3)
    for (const t of top) lines.push(`  · ${t.item}: ${fmt(t.amount)}${t.paid ? ' (paid)' : ''}`)
  } else {
    lines.push('', '_No budget file yet — send "budget 48000" to set your cap; parsed quotes fill in the committed lines._')
  }

  lines.push('', '_reply "report" any time · auto-sent every Monday 9am_')
  return lines.join('\n')
}
