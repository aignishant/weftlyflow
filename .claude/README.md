# .claude/ — Weftlyflow Claude Code config

Project-scoped configuration for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Mirrors the structure of `low-spec-2/.claude` but rewritten for Weftlyflow's domain (workflow automation, not ML).

## Layout

```
.claude/
├── CLAUDE.md              project memory (always loaded)
├── README.md              this file
├── settings.json          committed permissions + hooks + env
├── settings.local.json    personal overrides (gitignored; copy from .example)
├── .mcp.json              MCP servers — filesystem, github, playwright, context7, …
├── agents/                9 subagents (code-reviewer, debugger, node-author, ip-checker, …)
├── skills/                on-demand + auto-triggered workflows
├── commands/              legacy /slash commands kept for compatibility
├── hooks/                 bash scripts for PreToolUse / PostToolUse / SessionStart / Stop
└── docs/                  deep-dive guides for Weftlyflow-specific Claude usage
```

## Quick links

- Canonical design doc: `/IMPLEMENTATION_BIBLE.md`
- Agents: `/agents` — spawn a subagent by name or let it auto-invoke.
- Skills: `/<skill-name>` — see `skills/README.md`.
- MCP: `/mcp` — verify which servers are live.
- Hooks: `hooks/hooks.json` — restart Claude Code after edits.

## First-time setup

```bash
cp .claude/settings.local.json.example .claude/settings.local.json
# (optional) edit .claude/settings.local.json to add tokens/env
# Restart Claude Code to pick up hooks.
```

Verify: `/doctor`, `/agents`, `/mcp`.
