// One-command judge demo: triage → RFQ → contractor shortlist → ledger → report.
//
//   npm run demo            offline — replays RECORDED outputs of the real pipeline
//   RENOGENT_LIVE=1 npm run demo   live — re-runs triage + RFQ through Claude
//
// Everything shown offline was produced by the live pipeline against
// data/fixtures/work-items.json; recordings live in demo/recorded/.
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
const REC = path.join(ROOT, 'demo/recorded')
const LIVE = process.env.RENOGENT_LIVE === '1'

// the report reads the ledger via env — point it at a throwaway copy seeded
// from fixtures so the demo never touches a real ledger
const DEMO_LEDGER = path.join(ROOT, 'demo/recorded/.demo-ledger.json')
process.env.RENOAI_LEDGER = DEMO_LEDGER

const hr = (t) => console.log(`\n${'─'.repeat(64)}\n${t}\n${'─'.repeat(64)}`)
const icon = { green: '🟢', amber: '🟡', red: '🔴', escalate: '🟣' }

hr(`RenoGent pipeline demo — ${LIVE ? 'LIVE (Claude)' : 'offline replay of recorded live runs'}`)
console.log('Input: data/fixtures/work-items.json (6 proposed work items on a real HDB 4-room plan)')

// ── 1 · compliance triage with machine-verified citations ──────────────
hr('1 · COMPLIANCE TRIAGE — every citation verbatim-verified against hdb.gov.sg corpus')
let triage
if (LIVE) {
  const { triage: run } = await import('../agent/compliance/triage.js')
  triage = await run(JSON.parse(fs.readFileSync(path.join(ROOT, 'data/fixtures/work-items.json'), 'utf8')))
} else {
  triage = JSON.parse(fs.readFileSync(path.join(REC, 'triage-output.json'), 'utf8'))
}
const items = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/fixtures/work-items.json'), 'utf8'))
for (const t of triage) {
  const item = items.find((i) => i.id === t.id)
  console.log(`\n${icon[t.classification] || '🟣'} ${t.id} ${item?.item || ''}`)
  console.log(`   ${t.reasoning.slice(0, 140)}`)
  for (const c of (t.citations || []).slice(0, 1))
    console.log(`   ${c.verified ? '✓ verified' : '✗ REJECTED'}: "${(c.quote || '').slice(0, 90)}…"\n     ${c.source_url}`)
}

// ── 2 · contractor-direct RFQ ───────────────────────────────────────────
hr('2 · RFQ — approved scope compiled into a line-item request for quotation')
let rfq
if (LIVE) {
  const { generateRfq } = await import('../agent/rfq/rfq.js')
  rfq = await generateRfq(triage, items)
} else {
  rfq = fs.readFileSync(path.join(REC, 'rfq-output.txt'), 'utf8')
}
console.log(rfq.split('\n').slice(0, 28).join('\n'))
console.log('   … (full RFQ in demo/recorded/rfq-output.txt)')

// ── 3 · DRC contractor shortlist (sample dataset) ───────────────────────
hr('3 · CONTRACTOR SHORTLIST — matched to scope from HDB DRC directory (sample data)')
const drc = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/fixtures/drc-contractors.json'), 'utf8'))
const scopeTrades = new Set(['flooring', 'hacking', 'electrical', 'carpentry'])
const matched = drc.contractors
  .map((c) => ({ ...c, hits: c.trades.filter((t) => scopeTrades.has(t)).length }))
  .filter((c) => c.hits > 0)
  .sort((a, b) => b.hits - a.hits || b.hdb_projects_5y - a.hdb_projects_5y)
  .slice(0, 3)
for (const c of matched)
  console.log(`   ${c.name} (${c.drc_no}) — trades: ${c.trades.join(', ')} · ${c.hdb_projects_5y} HDB projects/5y · ${c.typical_band} band`)
console.log(`   (${drc._note})`)

// ── 4 · commitment ledger + weekly report ───────────────────────────────
hr('4 · SUPERVISION — promises → ledger → slippage → weekly report with acceptance checklists')
fs.mkdirSync(REC, { recursive: true })
fs.rmSync(DEMO_LEDGER, { force: true })
const ledger = await import('../agent/ledger/ledger.js')
const seed = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/fixtures/seed-commitments.json'), 'utf8'))
for (const e of seed) ledger.append(e)
ledger.resolve('C002') // carpentry closed this week → acceptance checklist shows up
console.log('   promises extracted from real WhatsApp messages → append-only ledger; slippage = date math, not vibes\n')
const { buildReport } = await import('../agent/ledger/report.js')
console.log(buildReport())

hr('That was the coordination layer an ID firm charges a 30-50% markup for.')
console.log('Live WhatsApp bridge (renders, approvals, chase drafts): npm run supervise')
console.log('Landing: https://littlejuju.github.io/RenoGent/  ·  every render audited, every send human-approved\n')
