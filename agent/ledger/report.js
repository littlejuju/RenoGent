// Progress + budget report — the PM layer over the commitment ledger.
// One WhatsApp-formatted digest: what's done, what's due, what slipped (the
// blockers), and budget committed vs. cap. On-demand via "report" in the
// console, and scheduled weekly by the supervisor.
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import * as ledger from './ledger.js'

const BUDGET_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../demo/budget.json')

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
