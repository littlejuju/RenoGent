// Contractor-direct RFQ: compile triaged scope into line-item RFQs, and parse
// returned quotes into the commitment ledger (price + scope + promised date
// per line item — so every quote becomes enforceable, not a PDF in a drawer).
//
// Usage: node agent/rfq/rfq.js generate demo/triage-output.json
//        node agent/rfq/rfq.js parse-quote data/fixtures/quote-sample.txt
import fs from 'fs'
import { askClaude, parseJson } from '../llm.js'
import * as ledger from '../ledger/ledger.js'

export async function generateRfq(triageResults, workItems) {
  const scope = triageResults
    .filter((r) => r.classification !== 'red')
    .map((r) => ({
      id: r.id,
      description: workItems.find((i) => i.id === r.id)?.description,
      compliance_conditions: r.classification === 'amber' ? r.reasoning : 'none',
    }))
  const text = await askClaude(
    `Compile this approved renovation scope into a professional line-item RFQ (request for quotation) that a Singapore HDB homeowner can send directly to a renovation contractor. For each line: item id, work description, compliance conditions the contractor must price in (permits, limits), and a blank unit-price column. Require: itemised pricing (no lump sums), committed completion date per line, DRC registration number. Plain text, ready to paste into WhatsApp/email.\n\nSCOPE:\n${JSON.stringify(scope, null, 2)}`,
    { maxTokens: 2000 }
  )
  return text.trim()
}

export async function parseQuote(quoteText) {
  const parsed = parseJson(
    await askClaude(
      `Parse this contractor quote into JSON: {"contractor": string, "lines": [{"item": string, "price_sgd": number|null, "promised_date": "YYYY-MM-DD"|null, "notes": string}], "red_flags": [string]}\nFlag: lump sums hiding itemisation, missing dates, vague scope words ("etc", "and so on"), prices wildly off for the item.\n\nQUOTE:\n"""${quoteText}"""`,
      { maxTokens: 2000 }
    )
  )
  for (const line of parsed.lines) {
    ledger.append({
      who: parsed.contractor,
      item: line.item,
      promised_date: line.promised_date,
      source_msg: `quote: ${line.item} @ S$${line.price_sgd}`,
      chat: 'RFQ',
      ts: new Date().toISOString(),
    })
  }
  return parsed
}

const [, , cmd, file] = process.argv
if (cmd === 'generate') {
  const triage = JSON.parse(fs.readFileSync(file, 'utf8'))
  const items = JSON.parse(fs.readFileSync('data/fixtures/work-items.json', 'utf8'))
  const rfq = await generateRfq(triage, items)
  fs.writeFileSync('demo/rfq-output.txt', rfq)
  console.log(rfq + '\n\nsaved -> demo/rfq-output.txt')
} else if (cmd === 'parse-quote') {
  const parsed = await parseQuote(fs.readFileSync(file, 'utf8'))
  console.log(JSON.stringify(parsed, null, 2))
  console.log(`\n${parsed.lines.length} quote lines appended to ledger`)
}
