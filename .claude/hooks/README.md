# Hooks

Declared in `hooks.json`. Scripts receive the tool-call JSON on stdin; exit `2` to block (stderr is shown to the model), `0` to allow.

| Script | Event | Purpose |
|---|---|---|
| `block-dangerous-bash.sh` | PreToolUse (Bash) | Refuse `rm -rf /`, `curl \| sh`, force-push to main, `git reset --hard`, `make db-reset`, etc. |
| `block-secret-writes.sh` | PreToolUse (Write\|Edit) | Refuse writes to `.env`, `.ssh/`, `secrets/`, `credentials.json`. Allows `.env.example`. |
| `block-n8n-copy.sh` | PreToolUse (Write\|Edit) | Refuse writes inside the n8n reference tree and content containing n8n-specific identifiers. |
| `post-edit-format.sh` | PostToolUse (Write\|Edit) | Run ruff/isort on `.py`, prettier on `.ts/.vue/.md/.json`. Never fails. |
| `session-start.sh` | SessionStart | Print branch, HEAD, dirty count. |
| `session-end.sh` | Stop | Quiet placeholder. |

After editing any of these files, restart Claude Code. Verify with `/hooks` and `/doctor`.
