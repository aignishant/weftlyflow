#!/usr/bin/env bash
# PreToolUse hook on the Bash tool — block obvious footguns even if an allow-rule slipped through.
# Exit 2 blocks; stderr reaches the model as feedback.
set -euo pipefail

input="$(cat)"
cmd="$(echo "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command",""))')"

# Patterns we never want to run.
patterns=(
  'rm -rf /'
  'rm -rf ~'
  'rm -rf \$HOME'
  ':\(\)\{:\|:&\};:'        # fork bomb
  'mkfs\.'
  'dd if=/dev/(zero|random)'
  '> /dev/sda'
  'chmod -R 777 /'
  'curl .* \| (sh|bash)'
  'wget .* \| (sh|bash)'
  'git push .*--force'
  'git push .* -f '
  'git push origin (main|master)'
  'git reset --hard'
  'git clean -fdx'
  'alembic downgrade base'
)

for p in "${patterns[@]}"; do
  if echo "$cmd" | grep -Eq "$p"; then
    echo "Blocked by Weftlyflow guard: command matches '$p'" >&2
    exit 2
  fi
done

exit 0
