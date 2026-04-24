"""AI nodes — LLM providers, agents, memory, vector stores, embeddings.

LangChain-Python is used internally for primitives (LLM clients, vector stores,
retrievers, memory) but **never leaks into Weftlyflow's public surface**. Every
AI node is a thin wrapper returning plain dicts.

Subpackages (added in Phase 7):
    llm_openai/, llm_anthropic/, llm_google/, llm_ollama/, llm_mistral/
    agent_react/, agent_openai_functions/, agent_anthropic_tools/
    memory_buffer/, memory_summary/, memory_window/
    vector_pgvector/, vector_qdrant/
    embed_openai/, embed_local/
    trigger_chat/, chat_respond/

See weftlyinfo.md §18.
"""

from __future__ import annotations
