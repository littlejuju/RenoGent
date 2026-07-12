// Generate room render candidates from cached floor-plan briefs, without Claude audit.
//
// Usage:
//   node demo/render_candidates_no_claude.js "study,bedroom 1" 2
//
// This is the fallback path when Claude quota is exhausted:
// Replicate generates candidates, then the release gate quarantines obvious
// failures before a human/Codex reviews anything.
import fs from 'fs'
import path from 'path'
import { execFile } from 'child_process'
import { promisify } from 'util'
import { fileURLToPath } from 'url'
import { setTimeout as sleep } from 'timers/promises'
import { roomPrompt } from '../agent/factlayer/render_all.js'
import { auditPromptContract } from '../agent/factlayer/meta_audit.js'
import { releaseGate } from '../agent/factlayer/release_gate.js'

const execFileP = promisify(execFile)
const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
const lastPlan = JSON.parse(fs.readFileSync(path.join(ROOT, 'demo/lastplan.json'), 'utf8'))
const briefsPath = lastPlan.file.replace(/\.[a-z]+$/i, '-briefs.json')
const briefs = JSON.parse(fs.readFileSync(briefsPath, 'utf8'))

const filter = (process.argv[2] || '').toLowerCase().split(',').map((s) => s.trim()).filter(Boolean)
const count = Number(process.argv[3] || 1)
const delayMs = Number(process.env.RENDER_CANDIDATE_DELAY_MS || 45000)
const rooms = briefs.rooms.filter((r) => !filter.length || filter.some((f) => r.name.toLowerCase().includes(f)))
const stamp = Date.now()

if (!rooms.length) {
  console.error(`No rooms matched filter: ${process.argv[2] || '(empty)'}`)
  process.exit(1)
}

const renderOne = async (room, i) => {
  const slug = room.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  const out = lastPlan.file.replace(/\.[a-z]+$/i, `-${slug}-manual-${stamp}-${i}.png`)
  const prompt =
    roomPrompt(room, lastPlan.style) +
    ' Produce a clean, realistic candidate for human audit. Prioritize exact room identity, side/bearing correctness, window/parapet typology, and no false ceiling unless explicitly requested. If the brief says no grid on window, render clear undivided glass without security grilles, muntins, louvres, horizontal bars or decorative slats. If a door, opening or threshold is listed as behind the camera or outside the view cone, crop it out completely, including its frame, leaf, handles and trim. Do not render plan labels or measurements.'
  const promptAudit = auditPromptContract(room, lastPlan.style, prompt)
  if (!promptAudit.pass) {
    throw new Error(`prompt failed meta-audit for ${room.name}: ${promptAudit.violations.map((v) => v.element).join(', ')}`)
  }
  console.log(`[render] ${room.name} candidate ${i} -> ${out}`)
  await execFileP('python3', [path.join(ROOT, 'agent/factlayer/render.py'), lastPlan.file, out, prompt], {
    timeout: 300000,
    maxBuffer: 4 * 1024 * 1024,
  })
  const gate = await releaseGate({
    roomName: room.name,
    renderPath: out,
    requireLocalHook: true,
  })
  const record = { room: room.name, candidate: i, file: out, promptAudit, releaseGate: gate }
  console.log(JSON.stringify(record))
  return record
}

const ok = []
const records = []
const quarantined = []
const failed = []
for (const room of rooms) {
  for (let i = 1; i <= count; i++) {
    try {
      const record = await renderOne(room, i)
      records.push(record)
      if (record.releaseGate.pass) {
        ok.push(record.file)
      } else {
        quarantined.push(record)
      }
    } catch (err) {
      failed.push(String(err?.message || err))
    }
    if (!(room === rooms.at(-1) && i === count)) {
      console.log(`[render] waiting ${Math.round(delayMs / 1000)}s before next candidate to avoid API rate limits`)
      await sleep(delayMs)
    }
  }
}
fs.writeFileSync(path.join(ROOT, 'demo/manual-candidates.json'), JSON.stringify({ ts: new Date().toISOString(), files: ok, records, quarantined, failed }, null, 2))
console.log(`done: ${records.length} generated, ${ok.length} release-ready, ${quarantined.length} quarantined, ${failed.length} failed -> demo/manual-candidates.json`)
if (failed.length || !ok.length) {
  console.error(failed.join('\n---\n'))
  process.exitCode = 1
}
