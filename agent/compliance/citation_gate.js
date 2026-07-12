// Citation-verification gate.
// A rule citation is only accepted if its quote appears VERBATIM in the
// scraped hdb.gov.sg corpus and its source_url matches the frontmatter of
// the file the quote was found in. Anything else is rejected — the agent
// is not allowed to paraphrase regulation into existence.
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const CORPUS_DIR = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../data/hdb_corpus'
)

const norm = (s) =>
  s
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, '-')
    .replace(/\s+/g, ' ')
    .trim()

let corpusCache = null
export function loadCorpus() {
  if (corpusCache) return corpusCache
  corpusCache = fs
    .readdirSync(CORPUS_DIR)
    .filter((f) => f.endsWith('.md') && !f.startsWith('_'))
    .map((f) => {
      const raw = fs.readFileSync(path.join(CORPUS_DIR, f), 'utf8')
      const url = raw.match(/^source_url:\s*(\S+)/m)?.[1] || ''
      return { file: f, source_url: url, raw, normed: norm(raw) }
    })
  return corpusCache
}

const MIN_QUOTE_CHARS = 20

// citations: [{quote, source_url}] -> [{...citation, verified, reason, file}]
export function verifyCitations(citations) {
  const corpus = loadCorpus()
  return citations.map((c) => {
    const q = norm(c.quote || '')
    if (q.length < MIN_QUOTE_CHARS)
      return { ...c, verified: false, reason: `quote too short (<${MIN_QUOTE_CHARS} chars) to be citation-grade` }
    const hit = corpus.find((doc) => doc.normed.includes(q))
    if (!hit)
      return { ...c, verified: false, reason: 'quote not found verbatim in corpus' }
    if (norm(c.source_url || '') !== norm(hit.source_url))
      return { ...c, verified: false, reason: `URL mismatch: quote lives in ${hit.file} (${hit.source_url})`, file: hit.file }
    return { ...c, verified: true, file: hit.file }
  })
}

export function corpusAsContext() {
  return loadCorpus()
    .map((d) => `<<<FILE ${d.file}>>>\n${d.raw}`)
    .join('\n\n')
}
