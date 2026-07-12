// LLM gateway — single entry point for every model call in RenoAI.
// Prefers the Anthropic SDK (ANTHROPIC_API_KEY); falls back to the local
// `claude -p` CLI so the demo can run on a Claude subscription.
import { execFileSync } from 'child_process'

const MODEL = process.env.RENOAI_MODEL || 'claude-sonnet-5'

export async function askClaude(prompt, { system = '', maxTokens = 4096 } = {}) {
  if (process.env.ANTHROPIC_API_KEY) {
    const { default: Anthropic } = await import('@anthropic-ai/sdk')
    const client = new Anthropic()
    const resp = await client.messages.create({
      model: MODEL,
      max_tokens: maxTokens,
      system: system || undefined,
      messages: [{ role: 'user', content: prompt }],
    })
    return resp.content.filter((b) => b.type === 'text').map((b) => b.text).join('')
  }
  const args = ['-p', '--model', MODEL]
  if (system) args.push('--append-system-prompt', system)
  return execFileSync('claude', args, {
    input: prompt,
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
    timeout: 300000,
  })
}

// Extract a JSON object/array from a model reply that may carry fences or prose.
export function parseJson(text) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/)
  const candidate = fenced ? fenced[1] : text
  const start = candidate.search(/[[{]/)
  if (start === -1) throw new Error(`no JSON found in model reply:\n${text.slice(0, 400)}`)
  return JSON.parse(candidate.slice(start).trim().replace(/[^}\]]*$/, ''))
}
