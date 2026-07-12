// Whole-flat render orchestrator: floor plan + homeowner style brief →
// one constrained render PER ROOM, each passed through the audit hook.
//
// Retry policy (bounded escalation, not infinite surgical retry):
//   up to 2 fresh BASE renders (base 2 bakes every earlier violation into the
//   prompt as explicit constraints) × up to 2 SURGICAL fix rounds per base,
//   with a plateau early-exit (if a fix round doesn't lower the violation
//   score, that base is a dead end — surgical edits inherit the broken image).
//   Every attempt is scored (L1/L2 fatal ×10, L3 ×1); the best one is released
//   even when it never passed — labelled honestly as NOT passed, with the
//   remaining issues, and the homeowner can reply "redo <room>" to try again.
import { execFile } from 'child_process'
import { promisify } from 'util'
import { createHash } from 'crypto'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { readPlanBriefs } from './plan_briefs.js'
import { auditRender } from './audit.js'

const execFileP = promisify(execFile)
const HERE = path.dirname(fileURLToPath(import.meta.url))

const MAX_BASES = 2
const MAX_FIX_ROUNDS = 2

const HDB_TYPOLOGY = (
  'This is a Singapore HDB flat. STRICT constraints: windows are standard HDB windows ' +
  'with a solid wall parapet below (sill about 1 metre above floor), casement or sliding ' +
  'panels in a horizontal band, modestly sized relative to the wall. Frame COLOUR and ' +
  'glazing style follow the homeowner brief (default dark aluminium ONLY if the brief is silent). ' +
  'ABSOLUTELY NO floor-to-ceiling windows, NO curtain walls, NO balcony unless the floor plan ' +
  'shows one. Flat concrete ceiling about 2.6m; false ceiling only as a perimeter L-box. ' +
  'KITCHEN RULE: the window sits ABOVE the counter and backsplash (sill ~1.1-1.2m); the sink ' +
  'may sit under the window but the window must never overlap or cut into counters or cabinets ' +
  '— fixtures and windows occupy separate vertical zones. '
)

const runRender = (src, dst, prompt) =>
  execFileP('python3', [path.join(HERE, 'render.py'), src, dst, prompt], { timeout: 240000 })

function roomPrompt(room, style) {
  const noWindows = !room.expected_components?.some((c) => /window/i.test(c.what)) && !/window band|window on|windows on/i.test(room.windows || '')
  return (
    `This image is a 2D architectural floor plan of a Singapore HDB flat. ` +
    `Generate a photorealistic interior render of the ${room.name} ONLY (approx ${room.approx_size_mm || 'as drawn'}). ` +
    `NEVER render any text, labels, dimension numbers or annotations from the plan into the image — no "DROP", no room names, no measurements anywhere. ` +
    `ORIENTATION IS ABSOLUTE: left/right as seen from the camera must match the plan exactly — NEVER mirror or swap sides. ` +
    (noWindows ? `THIS ROOM HAS NO WINDOWS on the plan — render ZERO windows; it is an internal room lit by ceiling fixtures only. ` : '') +
    (room.fixtures ? `Sanitary/kitchen fixtures EXACTLY as drawn on the plan: ${room.fixtures}. Never add a fixture the plan does not show in this room (e.g. no toilet in the bathroom when the toilet pan is drawn in the separate W.C.). ` : '') +
    `Camera: ${room.camera}. ` +
    (room.visible_from_camera ? `FROM THIS EXACT CAMERA the visible features are: ${room.visible_from_camera}. Place every feature on the correct side. ` : '') +
    (room.expected_components?.length ? `The view must contain EXACTLY these architectural components, nothing more, nothing less: ${JSON.stringify(room.expected_components)}. ` : '') +
    (room.actual_function ? `Space function (geometry-verified, may differ from the plan label): ${room.actual_function}. Design for this ACTUAL function. ` : '') +
    (room.design_notes ? `Design decisions to follow (each has a circulation reason): ${room.design_notes}. No unjustified special elements. ` : '') +
    `Windows: ${room.windows || 'as drawn on the plan'}. Doors: ${room.doors || 'as drawn'}. ` +
    `${room.render_brief || ''} ` + HDB_TYPOLOGY +
    `Renovation style requested by the homeowner: ${style}. ` +
    `HOMEOWNER VETOES OVERRIDE THE DEFAULT LOOK: any brief item phrased as a prohibition ` +
    `("no grid on window", "no false ceiling") is a HARD constraint — "no grid" means ` +
    `single undivided glass panes: no muntins, no louvres, no slats.`
  )
}

const shortHash = (file) => createHash('sha256').update(fs.readFileSync(file)).digest('hex').slice(0, 8)

// L1/L2 (components, depth/scale) are fatal → weight 10; L3 style → 1.
// No audit result at all is worse than any audited attempt.
const isFatal = (v) => v.layer === 1 || v.layer === 2 || /component|structure|room-identity|depth|artifact/.test(v.element || '')
const fatalCount = (audit) => (audit?.violations || []).filter(isFatal).length
const scoreAudit = (audit) => {
  if (!audit) return 999
  if (audit.pass) return 0
  return (audit.violations || []).reduce((s, v) => s + (isFatal(v) ? 10 : 1), 0)
}

// one viewpoint-plan PER RENDER, stamped with the render's hash so the pair
// (render ↔ where-the-camera-stands) is verifiable and can't be mixed up
async function annotateCamera(planPath, room, slug, hash) {
  if (!room.camera_px || !room.look_at_px) return null
  const out = planPath.replace(/\.[a-z]+$/i, `-${slug}-cam-${hash}.jpg`)
  try {
    await execFileP('python3', [path.join(HERE, 'annotate.py'), planPath, out,
      String(room.camera_px.x), String(room.camera_px.y),
      String(room.look_at_px.x), String(room.look_at_px.y), `${room.name} · render #${hash}`], { timeout: 30000 })
    return out
  } catch { return null }
}

async function attemptRoom(planPath, room, slug, style, onProgress) {
  const candidates = []
  const auditOnce = async (file, camPlan) => {
    try {
      return await auditRender(path.resolve(camPlan || planPath), path.resolve(file), style, room.name, room.expected_components, room.approx_size_mm || '')
    } catch { return null }
  }
  const record = async (file) => {
    const hash = shortHash(file)
    const cameraPlan = await annotateCamera(planPath, room, slug, hash)
    await onProgress('audit', room, null)
    const audit = await auditOnce(file, cameraPlan)
    const c = { file, hash, cameraPlan, audit, score: scoreAudit(audit) }
    candidates.push(c)
    return c
  }

  for (let base = 1; base <= MAX_BASES; base++) {
    // base 2+ re-generates from scratch, carrying every violation seen so far
    // as explicit constraints — surgical edits can't escape a broken base image
    const learned = base > 1
      ? ` A PREVIOUS ATTEMPT FAILED THE PLAN AUDIT — this render MUST additionally satisfy: ${
          [...new Set(candidates.flatMap((c) => c.audit?.violations || []).map((v) => v.edit_instruction))].join(' ')}`
      : ''
    const baseFile = planPath.replace(/\.[a-z]+$/i, `-${slug}-a${base}.png`)
    await onProgress('render', room, base > 1 ? { retry_base: base } : null)
    await runRender(planPath, baseFile, roomPrompt(room, style) + learned)
    let cur = await record(baseFile)
    if (cur.audit?.pass) return { candidates, best: cur }

    for (let round = 1; round <= MAX_FIX_ROUNDS; round++) {
      if (!cur.audit?.violations?.length) break
      await onProgress('fix', room, cur.audit)
      const fixes = cur.audit.violations.map((v) => v.edit_instruction).join(' ')
      const fixedFile = planPath.replace(/\.[a-z]+$/i, `-${slug}-a${base}f${round}.png`)
      await runRender(cur.file, fixedFile, `${fixes} Change ONLY these elements; keep everything else identical. ` + HDB_TYPOLOGY +
        ` Homeowner vetoes still apply and override the default look: ${style}`)
      const next = await record(fixedFile)
      if (next.audit?.pass) return { candidates, best: next }
      if (next.score >= cur.score) break // plateau: this base is a dead end, try a fresh base
      cur = next
    }
  }
  // HARD RULE: an image with structural (L1/L2) violations is NEVER released.
  // Only structurally-clean candidates are eligible; style issues (L3) may ship
  // with a warning because taste is the human's call — geometry is not.
  const eligible = candidates.filter((c) => c.audit && fatalCount(c.audit) === 0)
  if (eligible.length) {
    const best = eligible.reduce((a, b) => (b.score < a.score ? b : a), eligible[0])
    return { candidates, best, blocked: false }
  }
  const closest = candidates.reduce((a, b) => (b.score < a.score ? b : a), candidates[0])
  return { candidates, best: closest, blocked: true }
}

// onProgress(stage, room, payload) — stages: briefs | render | audit | fix | done | error
// roomFilter: substring match on room name → re-render just that room ("redo kitchen"),
// reusing the persisted briefs instead of re-reading the plan.
export async function renderAllRooms(planPath, style, onProgress = () => {}, roomFilter = null) {
  // briefs cache is keyed to the plan file path — a re-upload gets a new
  // filename, so an existing cache is always valid for this exact plan
  const briefsPath = planPath.replace(/\.[a-z]+$/i, '-briefs.json')
  let briefs
  if (fs.existsSync(briefsPath)) {
    briefs = JSON.parse(fs.readFileSync(briefsPath, 'utf8'))
  } else {
    await onProgress('briefs', null, null)
    // the homeowner's brief informs room identification (they know their flat:
    // "the study" must become its own room even if the plan draws it like a porch)
    briefs = await readPlanBriefs(path.resolve(planPath), style)
    if (!briefs.is_floor_plan) return { is_floor_plan: false, results: [] }
    // persist the fact layer: briefs are the single source of truth for both the
    // renderer and the auditor — they must be reviewable after the fact
    fs.writeFileSync(briefsPath, JSON.stringify(briefs, null, 2))
  }
  const rooms = briefs.rooms.filter((r) => !roomFilter || r.name.toLowerCase().includes(roomFilter.toLowerCase()))
  const results = []
  for (const room of rooms) {
    const slug = room.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
    try {
      await onProgress('render', room, null)
      const { candidates, best, blocked } = await attemptRoom(planPath, room, slug, style, onProgress)
      const status = blocked ? 'blocked' : best.audit?.pass ? 'passed' : 'style-escalation'
      const r = {
        room: room.name,
        // blocked rooms release NO image — the file stays on disk for forensics only
        file: blocked ? null : best.file,
        blockedFile: blocked ? best.file : null,
        hash: best.hash, cameraPlan: blocked ? null : best.cameraPlan,
        audit: best.audit, status, attempts: candidates.length,
      }
      results.push(r)
      fs.appendFileSync(path.join(path.dirname(planPath), 'render-audit-log.jsonl'),
        JSON.stringify({ ts: new Date().toISOString(), room: room.name, hash: best.hash, render: best.file, viewpoint_plan: best.cameraPlan, status, attempts: candidates.length, attempt_scores: candidates.map((c) => c.score), audit_pass: best.audit?.pass ?? null, violations: best.audit?.violations?.length ?? null, audit: best.audit }) + '\n')
      await onProgress('done', room, r)
    } catch (e) {
      results.push({ room: room.name, error: e.message })
      await onProgress('error', room, e.message)
    }
  }
  return { is_floor_plan: true, results }
}
