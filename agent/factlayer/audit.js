// Render audit hook — machine-checks a render against the plan/photo ground
// truth in three ordered layers:
//   L1 components (walls, doors, windows, beams, columns) — manifest reconcile
//   L2 depth & scale (景深/尺度) — room proportions vs the plan's printed mm
//   L3 typology & style compliance (HDB rules, brief adherence)
// L1/L2 violations are fatal. Violations come back as surgical edit instructions.
import { execFile } from 'child_process'
import { promisify } from 'util'
import { parseJson } from '../llm.js'

const execFileP = promisify(execFile)
const MODEL = process.env.RENOAI_MODEL || 'claude-sonnet-5'

export async function auditRender(originalPath, renderPath, brief = '', expectedRoom = '', expectedComponents = null, sizeMm = '') {
  const manifest = expectedComponents?.length
    ? `EXPECTED COMPONENT MANIFEST (traced from the plan for this exact camera — the complete list of what the render may contain):
${JSON.stringify(expectedComponents, null, 1)}`
    : ''
  const prompt = `Read and visually compare these two images:
ORIGINAL (ground truth / fact layer): ${originalPath}
AI RENDER after renovation: ${renderPath}
${brief ? `Renovation brief (changes the brief requests are ALLOWED, but only where the plan geometry permits them): ${brief}` : ''}
${expectedRoom ? `The render is SUPPOSED to depict: ${expectedRoom}${sizeMm ? ` (approx ${sizeMm} per the plan's printed dimensions)` : ''}.` : ''}
${manifest}
If the ORIGINAL is a floor plan with a RED DOT + ARROW/CONE marker: that marks the exact camera position and view direction the render MUST match.

Audit in THREE LAYERS, in this exact order. Layer 1 and 2 violations are FATAL (pass=false regardless of layer 3).

LAYER 1 — COMPONENTS (walls, doors, windows, openings, beams, columns):
Step A: look ONLY at the render and list every architectural component you see, with bearing left/center/right and near/far. Ignore furniture.
Step A2 (independent viewpoint check — do this BEFORE consulting the manifest): the ORIGINAL shows the ENTIRE floor plan. From your Step A component list alone, judge which room and camera position on the plan this render actually matches best — it may NOT be the marked one. If the render matches a different room or a different viewpoint better than the marked camera (e.g. it reads as "bedroom looking into the study" rather than the marked position), that is a room-identity violation; name the room/viewpoint it actually resembles and the components that gave it away.
Step B: reconcile against the manifest (or, without a manifest, against the marked view cone on the plan):
  - manifest component MISSING → violation (component-missing)
  - render component NOT in the manifest → violation (component-invented), UNLESS the brief explicitly justifies it AND the plan geometry permits it there (e.g. "open concept kitchen" may only open the wall that actually borders the kitchen, in its actual position)
  - present but wrong bearing/side → violation (component-misplaced)
  - beams/columns on the plan inside the view must appear (structure)
  - any plan text leaked into the render — dimension numbers, room labels, "DROP", annotation arrows on floors or walls — is a violation (element: "artifact", layer 1, fatal)
Room identity follows from this layer: if the component set matches a different room or no room, that is a room-identity violation.

LAYER 2 — DEPTH & SCALE (景深/尺度):
  - Room proportions must match the plan dimensions${sizeMm ? ` (${sizeMm})` : ''}: a 2.9m-wide bedroom must not render like a 5m hall; distance to the far wall must be plausible for the plan.
  - Manifest distances (near/far) must be respected — a "far" hallway opening must not appear adjacent to the camera.
  - Ceiling height ~2.6m; window band length proportional to its wall segment on the plan.

LAYER 3 — TYPOLOGY & STYLE COMPLIANCE (only after layers 1-2):
  - HDB typology: horizontal window band with solid parapet below (sill ~1m; kitchen sill above counter at ~1.1-1.2m), modest size relative to the wall. No floor-to-ceiling windows, curtain walls, or balconies absent from the plan. Windows never overlap counters, sinks or cabinets.
  - Brief REQUESTS are binding finishes: if the brief specifies a frame colour, wall colour or material ("warm ivory window frame"), a render that contradicts it is a style violation — check colours item by item against the brief.
  - False ceiling only as perimeter L-box unless the brief says otherwise; style follows the brief.
  - Brief PROHIBITIONS are hard: any brief item phrased as "no X" ("no grid on window", "no false ceiling") that the render contradicts is a violation — muntins, louvres or slats all count as "grid".
  - Fixtures must match the plan: a fixture rendered in a room whose plan symbol sits in a different room (e.g. toilet in BATH when the pan is drawn in the W.C.) is a layer-1 component-invented violation.

Output pure JSON only, no prose:
{"room": "which room + camera position, or 'unverifiable'", "components_seen": ["render components with bearings"], "scale_check": "one line: do proportions/depth match the plan dims?", "pass": bool, "violations": [{"layer": 1, "element": "component-missing|component-invented|component-misplaced|structure|room-identity|artifact|depth-scale|hdb-typology|window|door|wall|ceiling|style", "evidence": "what is wrong, referencing position", "edit_instruction": "ONE surgical sentence for an image-edit model changing ONLY the offending element"}]}`
  const { stdout } = await execFileP('claude', ['-p', prompt, '--model', MODEL, '--allowedTools', 'Read'], {
    encoding: 'utf8',
    timeout: 420000,
    maxBuffer: 8 * 1024 * 1024,
  })
  return parseJson(stdout)
}
