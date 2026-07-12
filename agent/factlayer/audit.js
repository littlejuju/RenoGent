// Render audit hook — machine-checks a render against the original image
// (photo or 2D floor plan) as ground truth, element by element:
// windows → doors → walls/geometry → ceiling → beams & columns.
// Violations come back as surgical edit instructions for the image model.
import { execFile } from 'child_process'
import { promisify } from 'util'
import { parseJson } from '../llm.js'

const execFileP = promisify(execFile)
const MODEL = process.env.RENOAI_MODEL || 'claude-sonnet-5'

export async function auditRender(originalPath, renderPath, brief = '', expectedRoom = '') {
  const prompt = `Read and visually compare these two images:
ORIGINAL (ground truth / fact layer): ${originalPath}
AI RENDER after renovation: ${renderPath}
${brief ? `Renovation brief (changes the brief requests are ALLOWED): ${brief}` : ''}
${expectedRoom ? `The render is SUPPOSED to depict: ${expectedRoom}. Judge room identity against the plan's geometry for THAT room (its window walls, door positions, proportions).` : ''}

Audit the RENDER against the ORIGINAL, strictest first:
0. ROOM IDENTITY: state which room of the original the render depicts and where the camera stands.${expectedRoom ? ` If it does not match the expected room (${expectedRoom}) — wrong window wall, wrong proportions, wrong adjacencies — that is a violation.` : ''} If the room cannot be identified from the geometry, that is itself a violation ("room identity unverifiable").
1. HDB TYPOLOGY (domain prior — Singapore public housing): windows must be a horizontal band with a solid parapet wall below (sill ~1m above floor), dark-framed casement/sliding panels. Floor-to-ceiling windows, curtain walls, or a balcony not present in the original = violation. Ceiling ~2.6m, false ceiling only as perimeter L-box.
2. WINDOWS: same count, same wall positions, same proportions as the original. Any extra or missing window = violation.
3. DOORS: same count and wall positions.
4. WALLS & GEOMETRY: same wall layout and camera angle; no invented openings, rooms or depth.
5. CEILING: same false-ceiling shape unless the brief changes it.
6. STRUCTURE: beams and columns visible in the original must remain in place.

Output pure JSON only, no prose:
{"room": "which room + camera position, or 'unverifiable'", "pass": bool, "violations": [{"element": "room-identity|hdb-typology|window|door|wall|ceiling|structure", "evidence": "what is wrong, referencing position", "edit_instruction": "ONE surgical sentence for an image-edit model changing ONLY the offending element"}]}`
  const { stdout } = await execFileP('claude', ['-p', prompt, '--model', MODEL, '--allowedTools', 'Read'], {
    encoding: 'utf8',
    timeout: 240000,
    maxBuffer: 8 * 1024 * 1024,
  })
  return parseJson(stdout)
}
