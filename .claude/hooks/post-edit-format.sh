#!/usr/bin/env bash
# PostToolUse hook on Write/Edit — run formatters on the changed file when applicable.
# Never fails — formatting issues should be surfaced by `make lint`, not block edits.
set -u

input="$(cat)"
path="$(echo "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))' 2>/dev/null || echo "")"

[ -z "$path" ] && exit 0
[ ! -f "$path" ] && exit 0

case "$path" in
  *.py)
    if command -v ruff >/dev/null 2>&1; then ruff format --quiet "$path" 2>/dev/null || true; fi
    if command -v isort >/dev/null 2>&1; then isort --quiet "$path" 2>/dev/null || true; fi
    ;;
  *.ts|*.tsx|*.js|*.jsx|*.vue|*.json|*.md|*.yaml|*.yml)
    if command -v prettier >/dev/null 2>&1; then prettier --write --loglevel warn "$path" 2>/dev/null || true; fi
    ;;
esac

exit 0
