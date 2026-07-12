#!/bin/bash
# Sanitize gate — pre-commit hook.
# Blocks any commit whose staged content matches a PII pattern.
# Patterns live OUTSIDE the repo (they are themselves sensitive):
#   $SANITIZE_PATTERNS or ../raw/sanitize-patterns.txt relative to repo root.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
PATTERNS="${SANITIZE_PATTERNS:-$REPO_ROOT/../raw/sanitize-patterns.txt}"

if [[ ! -f "$PATTERNS" ]]; then
  echo "sanitize_gate: FATAL — patterns file not found at $PATTERNS" >&2
  echo "Refusing to commit without the PII blocklist." >&2
  exit 1
fi

fail=0
while IFS= read -r pat; do
  [[ -z "$pat" || "$pat" == \#* ]] && continue
  # search staged file contents
  hits=$(git diff --cached -U0 | grep -inE "$pat" || true)
  if [[ -n "$hits" ]]; then
    echo "sanitize_gate: BLOCKED — staged content matches PII pattern: $pat" >&2
    echo "$hits" | head -5 >&2
    fail=1
  fi
  # search staged file names
  namehits=$(git diff --cached --name-only | grep -inE "$pat" || true)
  if [[ -n "$namehits" ]]; then
    echo "sanitize_gate: BLOCKED — staged filename matches PII pattern: $pat" >&2
    fail=1
  fi
done < "$PATTERNS"

if [[ $fail -eq 1 ]]; then
  echo "" >&2
  echo "Commit rejected by sanitize gate. Redact and retry." >&2
  exit 1
fi
exit 0
