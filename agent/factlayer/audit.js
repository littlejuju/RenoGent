// Render audit hook — machine-checks a render against the original image
// (photo or 2D floor plan) as ground truth, element by element:
// windows → doors → walls/geometry → ceiling → beams & columns.
// Violations come back as surgical edit instructions for the image model.
import { execFile } from 'child_process'
import { promisify } from 'util'
import { parseJson } from '../llm.js'

const execFileP = promisify(execFile)
const MODEL = process.env.RENOAI_MODEL || 'claude-sonnet-5'

export async function auditRender(originalPath, renderPath, brief = '') {
  const prompt = `Read and visually compare these two images:
ORIGINAL (ground truth / fact layer): ${originalPath}
AI RENDER after renovation: ${renderPath}
${brief ? `Renovation brief (changes the brief requests are ALLOWED): ${brief}` : ''}

Audit the RENDER against the ORIGINAL, strictest first:
1. WINDOWS: same count, same wall positions, same proportions. Any extra or missing window = violation.
2. DOORS: same count and wall positions.
3. WALLS & GEOMETRY: same wall layout and camera angle; no invented openings, rooms or depth.
4. CEILING: same false-ceiling shape unless the brief changes it.
5. STRUCTURE: beams and columns visible in the original must remain in place.

Output pure JSON only, no prose:
{"pass": bool, "violations": [{"element": "window|door|wall|ceiling|structure", "evidence": "what is wrong, referencing position", "edit_instruction": "ONE surgical sentence for an image-edit model changing ONLY the offending element"}]}`
  const { stdout } = await execFileP('claude', ['-p', prompt, '--model', MODEL, '--allowedTools', 'Read'], {
    encoding: 'utf8',
    timeout: 240000,
    maxBuffer: 8 * 1024 * 1024,
  })
  return parseJson(stdout)
}
