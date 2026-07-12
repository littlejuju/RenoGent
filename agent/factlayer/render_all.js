// Whole-flat render orchestrator: floor plan + homeowner style brief →
// one constrained render PER ROOM, each passed through the audit hook
// (generate → audit vs plan → surgical re-edit → re-audit).
import { execFile } from 'child_process'
import { promisify } from 'util'
import path from 'path'
import { fileURLToPath } from 'url'
import { readPlanBriefs } from './plan_briefs.js'
import { auditRender } from './audit.js'

const execFileP = promisify(execFile)
const HERE = path.dirname(fileURLToPath(import.meta.url))

const HDB_TYPOLOGY = (
  'This is a Singapore HDB flat. STRICT constraints: windows are standard HDB windows ' +
  'with a solid wall parapet below (sill about 1 metre above floor), dark aluminium ' +
  'framed casement or sliding panels in a horizontal band. ABSOLUTELY NO floor-to-ceiling ' +
  'windows, NO curtain walls, NO balcony unless the floor plan shows one. Flat concrete ' +
  'ceiling about 2.6m; false ceiling only as a perimeter L-box. '
)

const runRender = (src, dst, prompt) =>
  execFileP('python3', [path.join(HERE, 'render.py'), src, dst, prompt], { timeout: 240000 })

function roomPrompt(room, style) {
  return (
    `This image is a 2D architectural floor plan of a Singapore HDB flat. ` +
    `Generate a photorealistic interior render of the ${room.name} ONLY (approx ${room.approx_size_mm || 'as drawn'}). ` +
    `Camera: ${room.camera}. ` +
    (room.visible_from_camera ? `FROM THIS EXACT CAMERA the visible features are: ${room.visible_from_camera}. Place every feature on the correct side. ` : '') +
    `Windows: ${room.windows || 'as drawn on the plan'}. Doors: ${room.doors || 'as drawn'}. ` +
    `${room.render_brief || ''} ` + HDB_TYPOLOGY +
    `Renovation style requested by the homeowner: ${style}`
  )
}

async function annotateCamera(planPath, room, slug) {
  if (!room.camera_px || !room.look_at_px) return null
  const out = planPath.replace(/\.[a-z]+$/i, `-${slug}-camera.jpg`)
  try {
    await execFileP('python3', [path.join(HERE, 'annotate.py'), planPath, out,
      String(room.camera_px.x), String(room.camera_px.y),
      String(room.look_at_px.x), String(room.look_at_px.y), room.name], { timeout: 30000 })
    return out
  } catch { return null }
}

// onProgress(stage, room, payload) — stages: briefs | render | audit | fix | done | error
export async function renderAllRooms(planPath, style, onProgress = () => {}) {
  await onProgress('briefs', null, null)
  const briefs = await readPlanBriefs(path.resolve(planPath))
  if (!briefs.is_floor_plan) return { is_floor_plan: false, results: [] }
  const results = []
  for (const room of briefs.rooms) {
    const slug = room.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
    let out = planPath.replace(/\.[a-z]+$/i, `-${slug}.png`)
    try {
      // camera marker on the plan: shown to the human, and the audit's ground truth
      const cameraPlan = await annotateCamera(planPath, room, slug)
      if (cameraPlan) await onProgress('camera', room, { file: cameraPlan })

      await onProgress('render', room, null)
      await runRender(planPath, out, roomPrompt(room, style))

      await onProgress('audit', room, null)
      let audit = null
      const groundTruth = cameraPlan || planPath
      try { audit = await auditRender(path.resolve(groundTruth), path.resolve(out), style, room.name) } catch {}

      if (audit && !audit.pass && audit.violations?.length) {
        await onProgress('fix', room, audit)
        const fixes = audit.violations.map((v) => v.edit_instruction).join(' ')
        const fixed = out.replace('.png', '-fixed.png')
        await runRender(out, fixed, `${fixes} Change ONLY these elements; keep everything else identical. ` + HDB_TYPOLOGY)
        out = fixed
        try { audit = await auditRender(path.resolve(groundTruth), path.resolve(out), style, room.name) } catch {}
      }
      const r = { room: room.name, file: out, audit }
      results.push(r)
      await onProgress('done', room, r)
    } catch (e) {
      results.push({ room: room.name, error: e.message })
      await onProgress('error', room, e.message)
    }
  }
  return { is_floor_plan: true, results }
}
