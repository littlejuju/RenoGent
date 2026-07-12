// Compliance triage — classify each proposed work item green/amber/red
// against the HDB rules corpus. Every classification must carry citations
// that survive the citation-verification gate; failures trigger ONE
// corrective retry, then escalate to the human.
//
// Usage: node agent/compliance/triage.js data/fixtures/work-items.json
import fs from 'fs'
import { askClaude, parseJson } from '../llm.js'
import { verifyCitations, corpusAsContext } from './citation_gate.js'

const SYSTEM = `You are the compliance module of RenoGent, an agent supervising an HDB flat renovation in Singapore.
Classify each proposed work item strictly against the provided official HDB corpus (scraped verbatim from hdb.gov.sg).
Rules:
- "green": clearly allowed without an HDB permit (may still need registered contractor).
- "amber": allowed only with conditions (permit required, dimensional limits, PE endorsement, timing limits). Name the exact conditions.
- "red": prohibited outright.
- Every classification MUST include 1-3 citations. Each citation = an EXACT VERBATIM substring copied character-for-character from the corpus (>= 20 chars, keep original wording, numbers and units) + the source_url from that file's frontmatter.
- Do NOT paraphrase inside "quote". Copy-paste exactness is machine-verified; paraphrased quotes will be rejected.
- If the corpus does not cover an item, classify "amber" with citations: [] and say so in reasoning — never invent a rule.
Output pure JSON: [{"id", "classification", "reasoning", "citations":[{"quote","source_url"}]}]`

async function classify(items, corpus, correction = '') {
  const prompt = `${correction}HDB RULES CORPUS:\n${corpus}\n\nPROPOSED WORK ITEMS:\n${JSON.stringify(items, null, 2)}\n\nClassify every item. JSON only.`
  return parseJson(await askClaude(prompt, { system: SYSTEM, maxTokens: 8000 }))
}

export async function triage(items) {
  const corpus = corpusAsContext()
  let results = await classify(items, corpus)

  // --- citation gate pass 1 ---
  results = results.map((r) => ({ ...r, citations: verifyCitations(r.citations || []) }))
  const failed = results.filter((r) => r.citations.some((c) => !c.verified))

  if (failed.length) {
    console.error(`[gate] ${failed.length} item(s) failed citation verification — corrective retry`)
    const retryItems = items.filter((i) => failed.some((f) => f.id === i.id))
    const correction =
      `CORRECTION PASS. Your previous citations for these items FAILED machine verification:\n` +
      failed
        .map((f) => `- item ${f.id}: ` + f.citations.filter((c) => !c.verified).map((c) => `"${(c.quote || '').slice(0, 60)}..." (${c.reason})`).join('; '))
        .join('\n') +
      `\nCopy quotes EXACTLY from the corpus this time.\n\n`
    const retried = (await classify(retryItems, corpus, correction)).map((r) => ({
      ...r,
      citations: verifyCitations(r.citations || []),
    }))
    results = results.map((r) => retried.find((x) => x.id === r.id) || r)
  }

  // --- final verdict: unverified citations escalate to human ---
  return results.map((r) => {
    const bad = (r.citations || []).filter((c) => !c.verified)
    if (bad.length)
      return { ...r, classification: 'escalate', escalation: 'CITATION GATE REJECTED — needs human review', }
    return r
  })
}

if (process.argv[1].endsWith('triage.js')) {
  const items = JSON.parse(fs.readFileSync(process.argv[2] || 'data/fixtures/work-items.json', 'utf8'))
  const out = await triage(items)
  const COLOR = { green: '\x1b[32m', amber: '\x1b[33m', red: '\x1b[31m', escalate: '\x1b[35m' }
  for (const r of out) {
    const item = items.find((i) => i.id === r.id)
    console.log(`\n${COLOR[r.classification]}● ${r.classification.toUpperCase()}\x1b[0m  ${item?.description || r.id}`)
    console.log(`  ${r.reasoning}`)
    for (const c of r.citations || [])
      console.log(`  ${c.verified ? '✓' : '✗'} "${c.quote.slice(0, 90)}${c.quote.length > 90 ? '…' : ''}"\n    ${c.source_url}${c.verified ? ' [verbatim-verified]' : ' [' + c.reason + ']'}`)
  }
  fs.writeFileSync('demo/triage-output.json', JSON.stringify(out, null, 2))
  console.log('\nsaved -> demo/triage-output.json')
}
