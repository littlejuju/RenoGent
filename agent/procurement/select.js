// Procurement selector: contractor sends a catalog (PDF or long text) →
// extract every option (price, material, color, durability) → apply the
// homeowner's requirements — and, when a learned decision profile exists,
// pick directly instead of asking (Phase B).
import { execFile } from 'child_process'
import { promisify } from 'util'
import { parseJson } from '../llm.js'
import { loadSkill, countDecisions, AUTO_THRESHOLD } from '../skills/skills.js'

const execFileP = promisify(execFile)
const MODEL = process.env.RENOAI_MODEL || 'claude-sonnet-5'

// filePath: pdf/image catalog (read via Claude's Read tool); textCatalog: inline text
export async function analyzeCatalog({ filePath = null, textCatalog = null, requirements, domainHint = '' }) {
  // domain is resolved first so we know whether a learned profile applies
  const source = filePath ? `Read the catalog file at: ${filePath}` : `CATALOG TEXT:\n"""${textCatalog}"""`

  const probe = await runClaude(`${source}\nWhat product domain is this catalog? Output pure JSON: {"domain": "kebab-case-slug e.g. vinyl-flooring"}`)
  const domain = (domainHint || parseJson(probe).domain || 'general').toLowerCase()

  const skill = loadSkill(domain)
  const auto = skill && countDecisions(domain) >= AUTO_THRESHOLD

  const prompt = `${source}

HOMEOWNER REQUIREMENTS: ${requirements}
${skill ? `LEARNED DECISION PROFILE (apply these rules as the homeowner's own judgment):\n${skill}` : ''}

Step 1: extract EVERY option in the catalog: {name, price (with unit), material, color, durability (wear layer/AC rating/warranty), notes}.
Step 2: score against the requirements${skill ? ' and the learned profile' : ''}.
${auto
    ? `Step 3: PICK exactly one, as the homeowner would. Output pure JSON:
{"domain":"${domain}","mode":"auto","pick":{name,price,material,color,durability,rationale},"applied_rules":["which profile rules drove this"],"runner_up":{name,why_not}}`
    : `Step 3: shortlist the TOP 3. Output pure JSON:
{"domain":"${domain}","mode":"top3","options":[{"label":"A","name":,"price":,"material":,"color":,"durability":,"pros":[2-3],"cons":[1-2]}, ...B, ...C],"excluded_because":"one line on what the rest failed on"}`}`

  const result = parseJson(await runClaude(prompt))
  result.domain = domain
  result.auto = !!auto
  return result
}

async function runClaude(prompt) {
  const { stdout } = await execFileP('claude', ['-p', prompt, '--model', MODEL, '--allowedTools', 'Read'], {
    encoding: 'utf8',
    timeout: 360000,
    maxBuffer: 16 * 1024 * 1024,
  })
  return stdout
}
