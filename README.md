# RenoAI — an AI renovator that replaces your interior designer's coordination layer

## TL;DR

- **Track:** OPC / Super Individuals (primary) — also fits Autonomous Agents
- **What:** An agentic service that gives Singapore HDB homeowners ID-level design, compliance and supervision — at contractor-direct prices. The agent does the coordination work an interior design firm charges 30–50% markup for; the human keeps taste sign-off and final approval.
- **Why us:** Built on a **real 9-month renovation dispute** — 2,171 WhatsApp messages between a homeowner and an ID firm (peak crisis month: 715 messages). Every demo step runs on this real data, not synthetic fixtures.
- **Where it lives:** Not another app. Renovation coordination in Singapore happens in WhatsApp — the agent rides the homeowner's own WhatsApp identity; approvals happen in your "Message Yourself" chat. Contractors see a well-organized homeowner, not a bot.
- **Stack:** Claude Code + Claude API (vision + tool use) for floor-plan reading, compliance triage and message drafting; Replicate (nano-banana) for structure-locked renders; whatsapp-web.js for a live WhatsApp supervision bridge.

## How you use it (no new app)

1. **Link once.** Scan a QR from your phone (WhatsApp → Linked Devices) — the exact same gesture as WhatsApp Web. That's the entire installation.
2. **Create your console.** Make a WhatsApp group for your household (you + spouse/family) — e.g. "RenoAI Console". Group membership is the permission system: anyone in it can feed the agent and approve its actions.
3. **Feed it.** Drop your floor plan or room photo into the console with a one-line brief ("hack the study wall, japandi style, S$50k"). The agent replies in the console with the verified structural fact layer, green/amber/red compliance triage (citations verbatim from hdb.gov.sg) and a structure-locked render.
4. **Supervise.** The agent watches your renovation group with contractors. Every promise ("tiling done by Friday") is logged to the commitment ledger; overdue promises trigger drafted chase messages delivered to your console — reply `ok 1` to send as yourself, `no 1` to discard. Either spouse can approve.

**Privacy model:** whitelist-only. The agent subscribes to exactly two chats — your console and your renovation group. Every other conversation is dropped at the event entry point: not read, not parsed, not stored. Every outgoing message requires explicit human approval.

## The 4-step agentic chain

1. **Floor plan → immutable fact layer.** mm/px calibration from printed dimension lines, structural extraction, verified overlays with read-back diff hooks.
2. **Compliance triage.** Work items classified green/amber/red against HDB rules; a citation-verification gate rejects any rule citation that does not verbatim-match our scraped hdb.gov.sg corpus (`data/hdb_corpus/`).
3. **Contractor-direct RFQ.** Scope → line-item RFQs → quotes parsed into a commitment ledger.
4. **WhatsApp supervision.** Live bridge logs contractor promises into the ledger, chases slippage, drafts escalations — a human approves every outgoing message before it is sent.

## Repo layout

```
agent/
  factlayer/    floor plan → verified structural overlay (+ diff hooks)
  compliance/   green/amber/red triage + citation-verification gate
  rfq/          RFQ generation + quote parsing
  ledger/       commitment ledger + slippage detection
  bridge/       WhatsApp bridge + human approval send-gate
data/
  hdb_corpus/   scraped hdb.gov.sg rules (citation ground truth)
  fixtures/     sanitized demo data
scripts/        sanitize gate (pre-commit PII blocker)
demo/           demo drivers
```

## Boundary

We do not replace licensed contractors or professional engineers; all structural works are executed by HDB-registered contractors under permit, and the agent's compliance output is decision support, with the homeowner holding final sign-off.

## What's real vs. staged (honest disclosure)

Real and working today: structure-locked render pipeline ($0.04/render), metric-grounded floor-plan extraction, WhatsApp bridge (live), 2,171-message parsed corpus, HDB rules corpus with citation gate. Hardcoded for the demo: payment, auth, multi-user persistence.
