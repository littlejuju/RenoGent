# Render Meta-Audit

RenoGent now treats render verification as two layers:

1. Primary visual audit: compare a render to the floor-plan fact layer.
2. Meta-audit: check whether the prompt and the audit result are themselves trustworthy.
3. Release gate: block any generated file from entering WhatsApp, docs, or manual candidate lists unless the applicable local hook also passes.

This prevents a bad image from passing just because the generator or auditor got confused by an inconsistent prompt.

## What The Meta-Audit Checks

- Render contract: splits each room into in-view components and off-camera components.
- Prompt preflight: rejects prompts that leak off-camera doors, openings, or thresholds as drawable objects.
- Veto expansion: turns homeowner constraints such as `no grid on window` and `no false ceiling` into model-resistant terms.
- Audit audit: rejects missing audit results, malformed audit JSON, or an audit that claims `pass` while still listing fatal L1/L2 violations.
- Release gate: separates generated PNGs from release-ready assets. Generated-but-failed files stay on disk for forensics only.
- Room hooks: deterministic local checks for known failure modes. Living/Dining currently blocks obvious window-grid and wrong-wall door/window compositions.

## Agent States

- `passed_primary`: the render matches the current fact-layer camera contract, primary audit passes, and meta-audit passes.
- `style_escalation`: structure is clean, but a taste/style veto needs human review.
- `alternate_asset`: the image is useful as design reference, but the primary camera contract does not match. The agent registers it with an alternate floor-plan camera annotation instead of counting it as a pass.
- `rejected`: room identity, structure, or scale is too wrong to use.

## Additional Assets

If a render has good design value but the viewpoint is not the primary contract, the agent can register it as an additional asset:

```bash
node demo/register_additional_asset.js \
  demo/inbox/plan-1783836724077-the-study-a1.png \
  "THE STUDY" \
  "Design reference is useful, but primary Study camera contract failed." \
  469 955 530 694 \
  demo/inbox/plan-1783836724077-the-study-cam-5ea0be03.jpg
```

This writes:

- `demo/inbox/additional-assets.jsonl`
- a sidecar `*-additional-asset.json`
- an alternate camera annotation `*-alt-cam-*.jpg`

Release rule: additional assets may be shown as design references, but must not be counted as primary fact-layer passes.

## Local Release Gate

Run a room-specific gate before showing any candidate:

```bash
npm run audit:render -- "LIVING/DINING" demo/inbox/plan-1783836724077-living-dining-regenerated-1.png
```

For the Living/Dining hook directly:

```bash
npm run audit:living -- demo/inbox/plan-1783836724077-living-dining-regenerated-1.png
```

Exit code `0` means the machine hook allows the image to proceed to human approval. Exit code `1` means it is quarantined and must not be posted or counted as passed.

## Code Entry Points

- `agent/factlayer/meta_audit.js`: render contract, prompt preflight, audit-result audit.
- `agent/factlayer/release_gate.js`: final machine gate before a render reaches any human-facing surface.
- `agent/factlayer/hooks/living_dining.py`: deterministic local quarantine hook for the Living/Dining same-wall door/window contract.
- `agent/factlayer/additional_assets.js`: additional asset registration.
- `agent/factlayer/render_all.js`: primary pass gate now requires visual audit and meta-audit.
- `demo/render_candidates_no_claude.js`: no-Claude local render candidates with prompt preflight and release-gate quarantine.
- `demo/register_additional_asset.js`: manual salvage path for alternate-view assets.
