# Weftlyflow

Self-hosted workflow automation platform — visual node-graph editor, triggers,
polling, hundreds of integrations, AI agents. Python backend, Vue 3 frontend.

!!! info "Status"
    Pre-alpha. Phase 0 (bootstrap) in progress.

## What Weftlyflow is

A workflow engine. You build a **workflow** — a directed graph of **nodes** connected by edges. A node is an action (call an API, transform data, run code) or a **trigger** (webhook, cron, poll). When a trigger fires, the engine walks the graph, passing **items** from node to node, and writes an **execution** record you can inspect afterwards.

## What Weftlyflow is not

- A drop-in replacement for n8n workflow JSON. Our schema is intentionally different.
- A hosted SaaS. Self-host first.
- An AI chat app — though it makes deploying a chat-triggered agent very easy.

## Quick links

- [Architecture](architecture.md) — the big picture in one page.
- [Getting started → Install](getting-started/install.md) — Docker or pip.
- [Getting started → Your first workflow](getting-started/first-workflow.md)
- [Guide → Expressions](guide/expressions.md) — how `{{ ... }}` resolves against run context.
- [Contributing → Node plugins](contributing/node-plugins.md) — add a new integration.
- [API reference](reference/index.md) — auto-generated from docstrings.

## Provenance

Weftlyflow is an **original Python implementation inspired by n8n's architecture**. It is not a fork. See [`IMPLEMENTATION_BIBLE.md §23`](https://example.com/weftlyflow/blob/main/IMPLEMENTATION_BIBLE.md) for the clean-room rules every contribution must follow.
