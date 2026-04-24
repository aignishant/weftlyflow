#!/usr/bin/env bash
# PreToolUse hook on Write/Edit — refuse to write content that looks copied from n8n.
# This is the last line of defense for the clean-room rules in weftlyinfo.md §23.
# It is heuristic — a true IP review is performed by the `ip-checker` agent on staged diffs.
set -euo pipefail

input="$(cat)"
content="$(echo "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("content","")+d.get("tool_input",{}).get("new_string",""))')"
path="$(echo "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))')"

# Never allow writing inside the reference n8n source tree.
case "$path" in
  */n8n-master/*)
    echo "Blocked: refusing to write into the n8n reference tree." >&2
    exit 2
    ;;
esac

# Heuristic: forbidden identifiers that are n8n-specific and must not appear in our source.
forbidden=(
  'n8n-nodes-base'
  'IExecuteFunctions'
  'IExecuteSingleFunctions'
  'IRunExecutionData'
  'ITriggerFunctions'
  'IPollFunctions'
  'INodeType'
  'INodeTypeDescription'
  'ICredentialType'
)

for f in "${forbidden[@]}"; do
  if echo "$content" | grep -Fq "$f"; then
    echo "Blocked: content contains n8n-specific identifier '$f'." >&2
    echo "Use the Weftlyflow equivalent (see weftlyinfo.md §23)." >&2
    exit 2
  fi
done

exit 0
