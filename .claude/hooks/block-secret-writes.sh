#!/usr/bin/env bash
# PreToolUse hook on Write/Edit — prevent committing secrets by accident.
set -euo pipefail

input="$(cat)"
path="$(echo "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))')"

case "$path" in
  *.env|*/.env|*/.env.*|*/.ssh/*|*/id_rsa|*/id_rsa.*|*/secrets/*|*/credentials.json)
    echo "Blocked by Weftlyflow guard: refusing to write to secret path '$path'" >&2
    exit 2
    ;;
esac

# .env.example is allowed.
case "$path" in
  */.env.example) exit 0 ;;
esac

exit 0
