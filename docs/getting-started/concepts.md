# Concepts

The shortest possible glossary. Full definitions live in `IMPLEMENTATION_BIBLE.md §3`.

| Term | One-liner |
|---|---|
| **Workflow** | A directed graph of nodes + connections. |
| **Node** | One step. Action, trigger, or poller. |
| **Connection** | Edge from one node's output port to another's input port. |
| **Port** | Typed socket on a node. Kind: `main`, `ai_tool`, `ai_memory`, ... |
| **Item** | One JSON record flowing between nodes. |
| **Execution** | One run of a workflow, with status and run data. |
| **Trigger** | Node that *starts* a workflow (manual, webhook, schedule, poll). |
| **Webhook** | HTTP endpoint registered by a trigger node. |
| **Expression** | `{{ ... }}` — resolved against run context (`$json`, `$input`, `$now`). |
| **Credential** | Encrypted auth blob (OAuth, API key, basic). |
| **Project** | Multi-tenancy unit. Users have roles per project. |
| **Static data** | Per-workflow persistent KV store (cursors, remembered IDs). |
| **Pin data** | Dev-only: hardcode a node's output to skip real API calls. |
