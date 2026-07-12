// Decision-learning skill store (Hermes-style self-composing skills).
//
// Phase A: the agent presents top-3 options; the human picks one. Every pick
// (chosen vs rejected + stated reason) is RECORDED.
// Synthesis: after each decision, Claude distills the full decision log into
// a human-readable skill file — explicit priority rules with confidence.
// Phase B: once a domain has >= AUTO_THRESHOLD decisions, the skill is applied
// directly: the agent picks 1 and the human only confirms (approval gate stays).
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { askClaude } from '../llm.js'

const DATA = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../demo/skills')
export const AUTO_THRESHOLD = 1 // demo: learn fast; production would be 3-5

const skillPath = (domain) => path.join(DATA, `${domain}.md`)
const decisionsPath = (domain) => path.join(DATA, `${domain}-decisions.jsonl`)

export function loadSkill(domain) {
  return fs.existsSync(skillPath(domain)) ? fs.readFileSync(skillPath(domain), 'utf8') : null
}

export function countDecisions(domain) {
  if (!fs.existsSync(decisionsPath(domain))) return 0
  return fs.readFileSync(decisionsPath(domain), 'utf8').trim().split('\n').filter(Boolean).length
}

export function recordDecision(domain, entry) {
  fs.mkdirSync(DATA, { recursive: true })
  fs.appendFileSync(decisionsPath(domain), JSON.stringify({ ts: new Date().toISOString(), ...entry }) + '\n')
}

export async function synthesizeSkill(domain) {
  const decisions = fs.readFileSync(decisionsPath(domain), 'utf8').trim()
  const existing = loadSkill(domain)
  const md = await askClaude(
    `You maintain the decision profile of a homeowner for the domain "${domain}".
DECISION LOG (each line: the options shown, which one the human chose, their stated reason):
${decisions}
${existing ? `EXISTING PROFILE (update it, don't start over):\n${existing}` : ''}

Distill this into a skill file the agent will use to choose on the human's behalf. Format:
# Decision profile: ${domain}
## Priority rules (ordered, with weights)
## Hard constraints (never violate)
## Taste notes
## Confidence: low/medium/high + why
Be concrete: numbers, thresholds, colors, materials — not vague adjectives. Only include rules actually evidenced by the log. Output the markdown only.`,
    { maxTokens: 1500 }
  )
  fs.mkdirSync(DATA, { recursive: true })
  fs.writeFileSync(skillPath(domain), md.trim())
  return md.trim()
}
