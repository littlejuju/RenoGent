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
     "render_brief": "one dense sentence for an image model: room shape, where the windows/doors are relative to camera, notable structure (beams, columns, service areas)"
   }
 ]
}
Rules:
- Include living/dining, kitchen, every bedroom, bathroom(s). Skip WC smaller than 2sqm, shelters, and corridors.
- Read window positions from the arc/line symbols on exterior walls; read dimensions from the printed mm numbers.
- Camera always stands at a doorway or room corner, looking toward the most characteristic wall (usually the window wall).
- Output pure JSON only.`
  const { stdout } = await execFileP('claude', ['-p', prompt, '--model', MODEL, '--allowedTools', 'Read'], {
    encoding: 'utf8',
    timeout: 300000,
    maxBuffer: 8 * 1024 * 1024,
  })
  return parseJson(stdout)
}
