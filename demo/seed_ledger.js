// Seed the commitment ledger with (sanitized) historical commitments so the
// demo starts with live state — including two already-slipped promises that
// the supervisor will chase on startup.
import fs from 'fs'
import * as ledger from '../agent/ledger/ledger.js'

const seeds = JSON.parse(fs.readFileSync(new URL('../data/fixtures/seed-commitments.json', import.meta.url), 'utf8'))
ledger.save([])
for (const s of seeds) console.log('seeded', ledger.append(s).id, '-', s.item)
console.log(`\nledger ready: ${ledger.open().length} open, ${ledger.slipped().length} already slipped`)
