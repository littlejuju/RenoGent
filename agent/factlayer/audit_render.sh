#!/bin/bash
# Render audit hook — the "generate → machine-audit → surgical re-edit" loop.
# Claude (vision) compares the render against the original photo and a rule
# list; any violation becomes a surgical edit instruction fed back to render.py.
#
# Usage: ./audit_render.sh <original.jpg> <render.png>
set -euo pipefail
ORIG="$1"; RENDER="$2"

claude -p --model claude-sonnet-5 <<EOF
Read these two images:
1. Original room photo: $(realpath "$ORIG")
2. AI render of the same room after renovation: $(realpath "$RENDER")

Audit the render against these rules:
- GEOMETRY: same walls, same window positions and count, same false-ceiling shape, same camera angle as the original.
- UX: sofa must face the TV wall; walkways >= 600mm implied clear; no furniture blocking windows or doors.
- REALISM: no warped lines, no impossible reflections, no floating objects.

Output pure JSON:
{"pass": bool, "violations": [{"rule": "...", "evidence": "...", "edit_instruction": "surgical one-sentence edit for an image model, change ONLY the offending element"}]}
EOF
