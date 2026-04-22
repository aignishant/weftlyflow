#!/usr/bin/env bash
# UserPromptSubmit hook — inject Karpathy Skills behavioral reminder
# into the model's context on every prompt. Non-blocking.
# Set KARPATHY_HOOK_DISABLED=1 to suppress without editing settings.json.
set -u

[[ "${KARPATHY_HOOK_DISABLED:-0}" = "1" ]] && exit 0

cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"Karpathy Skills reminder: (1) Think Before Coding — state assumptions, surface tradeoffs, ask when unclear. (2) Simplicity First — minimum code, no speculative abstractions, no error handling for impossible scenarios. (3) Surgical Changes — every changed line must trace to the request; do not refactor adjacent code. (4) Goal-Driven Execution — define success criteria as step->verify before coding."}}
JSON

exit 0
