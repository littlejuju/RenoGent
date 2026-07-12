// Whole-flat render orchestrator: floor plan + homeowner style brief →
// one constrained render PER ROOM, each passed through the audit hook
// (generate → audit vs plan → surgical re-edit → re-audit).
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

// onProgress(stage, room, payload) — stages: briefs | render | audit | fix | done | error
export async function renderAllRooms(planPath, style, onProgress = () => {}) {
  await onProgress('briefs', null, null)
  const briefs = await readPlanBriefs(path.resolve(planPath))
  if (!briefs.is_floor_plan) return { is_floor_plan: false, results: [] }
  // persist the fact layer: briefs are the single source of truth for both the
  // renderer and the auditor — they must be reviewable after the fact
  fs.writeFileSync(planPath.replace(/\.[a-z]+$/i, '-briefs.json'), JSON.stringify(briefs, null, 2))
  const results = []
  for (const room of briefs.rooms) {
    const slug = room.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
    let out = planPath.replace(/\.[a-z]+$/i, `-${slug}.png`)
    try {
      await onProgress('render', room, null)
      await runRender(planPath, out, roomPrompt(room, style))

      // pair the render with its viewpoint-plan via content hash, then audit the PAIR
      let hash = shortHash(out)
      let cameraPlan = await annotateCamera(planPath, room, slug, hash)
      await onProgress('audit', room, null)
      let audit = null
      try { audit = await auditRender(path.resolve(cameraPlan || planPath), path.resolve(out), style, room.name, room.expected_components, room.approx_size_mm || '') } catch {}

      let round = 0
      while (audit && !audit.pass && audit.violations?.length && round < 2) {
        round++
        await onProgress('fix', room, audit)
        const fixes = audit.violations.map((v) => v.edit_instruction).join(' ')
        const fixed = planPath.replace(/\.[a-z]+$/i, `-${slug}-fix${round}.png`)
        await runRender(out, fixed, `${fixes} Change ONLY these elements; keep everything else identical. ` + HDB_TYPOLOGY +
          ` Homeowner vetoes still apply and override the default look: ${style}`)
        out = fixed
        hash = shortHash(out)
        cameraPlan = await annotateCamera(planPath, room, slug, hash) // re-stamp for the fixed render
        try { audit = await auditRender(path.resolve(cameraPlan || planPath), path.resolve(out), style, room.name, room.expected_components, room.approx_size_mm || '') } catch {}
      }
      const r = { room: room.name, file: out, hash, cameraPlan, audit }
      results.push(r)
      fs.appendFileSync(path.join(path.dirname(planPath), 'render-audit-log.jsonl'),
        JSON.stringify({ ts: new Date().toISOString(), room: room.name, hash, render: out, viewpoint_plan: cameraPlan, audit_pass: audit?.pass ?? null, violations: audit?.violations?.length ?? null, audit }) + '\n')
      await onProgress('done', room, r)
    } catch (e) {
      results.push({ room: room.name, error: e.message })
      await onProgress('error', room, e.message)
    }
  }
  return { is_floor_plan: true, results }
}
