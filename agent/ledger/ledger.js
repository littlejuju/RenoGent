// Commitment ledger — the append-only memory that makes promises enforceable.
// Every contractor commitment extracted from chat lands here; slippage is a
// mechanical date comparison, not a vibe.
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const LEDGER_PATH =
  process.env.RENOAI_LEDGER ||
  path.join(path.dirname(fileURLToPath(import.meta.url)), '../../demo/ledger.json')

export function load() {
  if (!fs.existsSync(LEDGER_PATH)) return []
  return JSON.parse(fs.readFileSync(LEDGER_PATH, 'utf8'))
}

export function save(entries) {
  fs.mkdirSync(path.dirname(LEDGER_PATH), { recursive: true })
  fs.writeFileSync(LEDGER_PATH, JSON.stringify(entries, null, 2))
}

// entry: {who, item, promised_date (YYYY-MM-DD|null), source_msg, chat, ts}
export function append(entry) {
  const entries = load()
  const id = 'C' + String(entries.length + 1).padStart(3, '0')
  const full = { id, status: 'open', logged_at: new Date().toISOString(), ...entry }
  entries.push(full)
  save(entries)
  return full
}

export function resolve(id, status = 'done') {
  const entries = load()
  const e = entries.find((x) => x.id === id)
  if (e) { e.status = status; e.resolved_at = new Date().toISOString(); save(entries) }
  return e
}

// Commitments whose promised date has passed and are still open.
export function slipped(today = new Date()) {
  const cutoff = today.toISOString().slice(0, 10)
  return load().filter((e) => e.status === 'open' && e.promised_date && e.promised_date < cutoff)
}

export function open() {
  return load().filter((e) => e.status === 'open')
}
