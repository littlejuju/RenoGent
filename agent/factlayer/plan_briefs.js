// Plan → structured per-room render briefs (the fact-layer step).
// Claude vision reads the 2D floor plan and emits one machine-usable brief per
// room: which walls carry windows/doors, room proportions, and a camera spec.
// Renders are then CONSTRAINED by these briefs instead of the model's fantasy.
import { execFile } from 'child_process'
import { promisify } from 'util'
import { parseJson } from '../llm.js'

const execFileP = promisify(execFile)
const MODEL = process.env.RENOAI_MODEL || 'claude-sonnet-5'

export async function readPlanBriefs(imagePath) {
  const prompt = `Read the image at: ${imagePath}

If it is NOT a 2D architectural floor plan (e.g. it is a photo of a room), output: {"is_floor_plan": false, "rooms": []}

If it IS a floor plan, extract EVERY habitable room and output pure JSON:
{
 "is_floor_plan": true,
 "rooms": [
   {
     "name": "LIVING/DINING",                  // exactly as labelled on the plan
     "approx_size_mm": "4648 x 4528",          // from printed dimension lines if present
     "windows": "continuous window band on the south exterior wall",  // wall + type
     "doors": "main entrance from corridor on the west; 2800mm opening to ex-balcony on the south-west",
     "adjacent": "kitchen to the north, bedroom 2 to the east",
     "camera": "standing at the main entrance looking south toward the window wall",
     "camera_px": {"x": 123, "y": 456},        // camera position in PIXEL coordinates of THIS image
     "look_at_px": {"x": 200, "y": 600},       // point the camera looks at, pixel coordinates
     "visible_from_camera": "window band on the LEFT wall, bedroom door straight AHEAD, kitchen opening on the RIGHT — list every wall feature by left/right/ahead",
     "expected_components": [
       // EXHAUSTIVE manifest of what a camera at camera_px facing look_at_px sees, traced on the plan.
       // Every wall segment, door, opening, window in the view cone — nothing else exists.
       {"what": "window band", "bearing": "ahead-right", "distance": "far", "notes": "south exterior wall"},
       {"what": "hallway opening with 3 bedroom doors", "bearing": "ahead", "distance": "far", "notes": "914mm opening"}
     ],
     "render_brief": "one dense sentence for an image model: room shape, where the windows/doors are relative to camera, notable structure (beams, columns, service areas)"
   }
 ]
}
Also add per room:
   "fixtures": "sanitary/kitchen fixtures ACTUALLY DRAWN in this room on the plan (toilet pan, basin, shower, bathtub, sink, stove) and where they sit. Read the fixture symbols carefully: if the toilet pan is drawn in the separate W.C., then the BATH has NO toilet — say so explicitly.",
   "actual_function": "what this space REALLY is, judged from geometry — HDB plans often mislabel: a 'BALCONY' beside the kitchen that is enclosed, corridor-shaped (narrow, pass-through, leads to W.C./service area) is actually a service passage/hallway, not a leisure balcony. State your judgement and the geometric evidence (width, access, adjacency).",
   "design_notes": "1-2 design decisions with REASONS grounded in circulation (动线): where people walk through this room, what must stay clear, why counters/half-walls/openings go where they go. Any special element (half-height wall, raised counter, island) MUST carry a justification or be omitted."

Rules:
- Include living/dining, kitchen, every bedroom, bathroom(s). Skip WC smaller than 2sqm, shelters, and corridors.
- SANITY-CHECK every label against its geometry before trusting it (mislabeled balconies are classic in HDB plans).
- Read window positions from the arc/line symbols on exterior walls; read dimensions from the printed mm numbers.
- Camera always stands at a doorway or room corner INSIDE the room, looking toward the most characteristic wall (usually the window wall).
- camera_px / look_at_px are pixel coordinates on the image as provided — be precise, they will be drawn on the plan and verified.
- visible_from_camera must be derivable from the plan geometry: for a camera at camera_px facing look_at_px, say which features fall LEFT / RIGHT / AHEAD.
- expected_components: trace the view cone on the plan and enumerate EVERY component it hits (walls, doors, openings, windows, thresholds) with bearing and distance. Include NON-RECTANGULAR geometry explicitly: angled/chamfered corners (corner units often have one, look for short diagonal dimension lines like "343"), columns, recesses — if the view cone hits an angled corner wall, it MUST be in the manifest with its bearing. This manifest is the ground truth a renderer must reproduce and an auditor will check item by item — completeness matters more than brevity.
- Output pure JSON only.`
  const { stdout } = await execFileP('claude', ['-p', prompt, '--model', MODEL, '--allowedTools', 'Read'], {
    encoding: 'utf8',
    timeout: 600000,
    maxBuffer: 8 * 1024 * 1024,
  })
  return parseJson(stdout)
}
