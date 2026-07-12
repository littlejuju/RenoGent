// Render audit hook — machine-checks a render against the original image
// (photo or 2D floor plan) as ground truth, element by element:
// windows → doors → walls/geometry → ceiling → beams & columns.
// Violations come back as surgical edit instructions for the image model.
import { execFile } from 'child_process'
import { promisify } from 'util'
import { parseJson } from '../llm.js'

const execFileP = promisify(execFile)
const MODEL = process.env.RENOAI_MODEL || 'claude-sonnet-5'

export async function auditRender(originalPath, renderPath, brief = '', expectedRoom = '', expectedComponents = null) {
  const manifest = expectedComponents?.length
    ? `EXPECTED COMPONENT MANIFEST (traced from the plan for this exact camera — this is the complete list of what the render may contain):
${JSON.stringify(expectedComponents, null, 1)}

TWO-STEP COMPONENT AUDIT (do this FIRST, before anything else):
Step A — look ONLY at the render: list every architectural component you see (windows, doors, openings, visible adjacent rooms, wall segments, thresholds) with bearing left/center/right and near/far. Ignore furniture.
Step B — reconcile against the manifest:
  - manifest component MISSING from the render → violation
  - render component NOT in the manifest → violation (invented geometry), UNLESS the renovation brief explicitly justifies it (e.g. "open concept kitchen" may open a wall THAT BORDERS THE KITCHEN per the plan — position must still match the plan)
  - component present but wrong bearing/distance → violation
` : ''
  const prompt = `Read and visually compare these two images:
ORIGINAL (ground truth / fact layer): ${originalPath}
AI RENDER after renovation: ${renderPath}
${brief ? `Renovation brief (changes the brief requests are ALLOWED): ${brief}` : ''}
${expectedRoom ? `The render is SUPPOSED to depict: ${expectedRoom}. Judge room identity against the plan's geometry for THAT room (its window walls, door positions, proportions).` : ''}
${manifest}

If the ORIGINAL is a floor plan with a RED DOT + ARROW/CONE marker: that marks the exact camera position and view direction the render MUST match. Derive what should be visible LEFT / RIGHT / AHEAD from that marker and verify the render against it.

Audit the RENDER against the ORIGINAL, strictest first:
0. ROOM IDENTITY: state which room of the original the render depicts and where the camera stands.${expectedRoom ? ` If it does not match the expected room (${expectedRoom}) — wrong window wall, wrong proportions, wrong adjacencies — that is a violation.` : ''} If the room cannot be identified from the geometry, that is itself a violation ("room identity unverifiable").
1. HDB TYPOLOGY (domain prior — Singapore public housing): windows must be a horizontal band with a solid parapet wall below (sill ~1m above floor; in kitchens the sill sits ABOVE the counter/backsplash at ~1.1-1.2m), dark-framed casement/sliding panels, modestly sized relative to the wall. Floor-to-ceiling windows, curtain walls, or a balcony not present in the original = violation. Windows overlapping/cutting into counters, sinks or cabinets = violation (fixtures and windows occupy separate vertical zones). Ceiling ~2.6m, false ceiling only as perimeter L-box.
2. WINDOWS: same count, same wall positions, same proportions as the original. Any extra or missing window = violation.
3. DOORS: same count and wall positions.
4. WALLS & GEOMETRY: same wall layout and camera angle; no invented openings, rooms or depth.
5. CEILING: same false-ceiling shape unless the brief changes it.
6. STRUCTURE: beams and columns visible in the original must remain in place.

Output pure JSON only, no prose:
{"room": "which room + camera position, or 'unverifiable'", "components_seen": ["what you saw in the render, with bearings"], "pass": bool, "violations": [{"element": "component-missing|component-invented|component-misplaced|room-identity|hdb-typology|window|door|wall|ceiling|structure", "evidence": "what is wrong, referencing position", "edit_instruction": "ONE surgical sentence for an image-edit model changing ONLY the offending element"}]}`
  const { stdout } = await execFileP('claude', ['-p', prompt, '--model', MODEL, '--allowedTools', 'Read'], {
    encoding: 'utf8',
    timeout: 240000,
    maxBuffer: 8 * 1024 * 1024,
  })
  return parseJson(stdout)
}
