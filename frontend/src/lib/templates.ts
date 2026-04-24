// Pre-built workflow templates. Each one is a complete automation that
// installs as a real workflow via POST /api/v1/workflows — the user lands
// in the editor with every node pre-wired and parameters filled with
// sensible defaults. Identifiers (`type: "weftlyflow.*"`) match the
// backend node registry so graphs execute as soon as credentials are
// supplied. Curated for daily-usage automations and popular agent flows.

import type { WorkflowConnection, WorkflowCreate, WorkflowNode } from "@/types/api";

export type TemplateTone = "blue" | "green" | "purple" | "amber" | "pink" | "teal";

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  category: "Notifications" | "Data" | "AI" | "DevOps" | "Growth" | "Support";
  tone: TemplateTone;
  /** Short tags rendered as chips. */
  stack: string[];
  /** Heroicon/lucide icon name for the card (we resolve in the UI). */
  icon: string;
  /** Returns the payload to POST to /workflows. */
  build(): WorkflowCreate;
}

// Helpers ------------------------------------------------------------------

let counter = 0;
function nodeId(prefix: string): string {
  counter += 1;
  return `tpl_${prefix}_${Date.now().toString(36)}_${counter}`;
}

function mkNode(
  type: string,
  name: string,
  position: [number, number],
  parameters: Record<string, unknown> = {},
): WorkflowNode {
  return {
    id: nodeId(type.split(".").pop() ?? "n"),
    name,
    type,
    type_version: 1,
    parameters,
    credentials: {},
    position,
    disabled: false,
    notes: null,
    continue_on_fail: false,
  };
}

function connect(
  source: WorkflowNode,
  target: WorkflowNode,
  sourcePort = "main",
  targetPort = "main",
): WorkflowConnection {
  return {
    source_node: source.id,
    target_node: target.id,
    source_port: sourcePort,
    target_port: targetPort,
    source_index: 0,
    target_index: 0,
  };
}

/** Chain a linear list of nodes — each emits into the next via `main`. */
function linearConnect(nodes: WorkflowNode[]): WorkflowConnection[] {
  const out: WorkflowConnection[] = [];
  for (let i = 0; i < nodes.length - 1; i += 1) {
    out.push(connect(nodes[i], nodes[i + 1]));
  }
  return out;
}

// Templates · daily utility ------------------------------------------------

/** 1 · Uptime guard — scheduled health check with Slack alert on failure. */
function buildUptimeGuard(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Every 5 minutes", [80, 200], {
    cron: "0 */5 * * * *",
  });
  const probe = mkNode("weftlyflow.http_request", "Ping API", [320, 200], {
    method: "GET",
    url: "https://api.example.com/healthz",
    timeout: 10,
  });
  const gate = mkNode("weftlyflow.if", "Status != 200?", [560, 200], {
    condition: "={{ $json.statusCode !== 200 }}",
  });
  const notify = mkNode("weftlyflow.slack", "Page oncall", [820, 120], {
    operation: "postMessage",
    channel: "#incidents",
    text: "🚨 API health check failed — status {{ $json.statusCode }} at {{ $now }}",
  });
  const ok = mkNode("weftlyflow.no_op", "Healthy", [820, 300]);
  return {
    name: "Uptime guard · 5-min health check",
    nodes: [trigger, probe, gate, notify, ok],
    connections: [connect(trigger, probe), connect(probe, gate), connect(gate, notify, "true"), connect(gate, ok, "false")],
    tags: ["monitoring", "slack", "scheduled"],
  };
}

/** 2 · Stripe → Slack order notifier (webhook ingestion → formatted Slack post). */
function buildOrderNotifier(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "Stripe webhook", [80, 200], {
    path: "stripe-orders",
    method: "POST",
  });
  const shape = mkNode("weftlyflow.set", "Shape payload", [320, 200], {
    values: {
      order_id: "={{ $json.data.object.id }}",
      amount: "={{ $json.data.object.amount_total / 100 }}",
      currency: "={{ $json.data.object.currency }}",
      email: "={{ $json.data.object.customer_details.email }}",
    },
  });
  const big = mkNode("weftlyflow.if", "Is whale?", [560, 200], {
    condition: "={{ $json.amount >= 500 }}",
  });
  const whale = mkNode("weftlyflow.slack", "VIP alert", [820, 120], {
    operation: "postMessage",
    channel: "#sales-vip",
    text: "🐋 Big order — {{ $json.amount }} {{ $json.currency }} from {{ $json.email }}",
  });
  const regular = mkNode("weftlyflow.slack", "Standard post", [820, 300], {
    operation: "postMessage",
    channel: "#orders",
    text: "🧾 Order {{ $json.order_id }} · {{ $json.amount }} {{ $json.currency }}",
  });
  return {
    name: "Stripe → Slack · Order notifier",
    nodes: [hook, shape, big, whale, regular],
    connections: [connect(hook, shape), connect(shape, big), connect(big, whale, "true"), connect(big, regular, "false")],
    tags: ["stripe", "slack", "webhook"],
  };
}

/** 3 · ETL · scheduled API pull → transform → Airtable upsert. */
function buildEtl(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Hourly @ :05", [80, 200], {
    cron: "0 5 * * * *",
  });
  const fetch = mkNode("weftlyflow.http_request", "GET /orders", [320, 200], {
    method: "GET",
    url: "https://api.example.com/v1/orders?since={{ $now.minus({ hours: 1 }).toISO() }}",
  });
  const batch = mkNode("weftlyflow.split_in_batches", "Chunks of 50", [560, 200], {
    batch_size: 50,
  });
  const transform = mkNode("weftlyflow.transform", "Normalise", [800, 200], {
    script: "item.amount_usd = (item.amount_cents || 0) / 100;\nitem.loaded_at = new Date().toISOString();\nreturn item;",
  });
  const rename = mkNode("weftlyflow.rename_keys", "Map to Airtable", [1040, 200], {
    map: {
      order_id: "Order ID",
      amount_usd: "Amount (USD)",
      email: "Customer Email",
      loaded_at: "Loaded At",
    },
  });
  const air = mkNode("weftlyflow.airtable", "Upsert row", [1280, 200], {
    operation: "upsert",
    base_id: "YOUR_BASE_ID",
    table: "Orders",
    key_field: "Order ID",
  });
  return {
    name: "ETL · API hourly → Airtable",
    nodes: [trigger, fetch, batch, transform, rename, air],
    connections: [
      connect(trigger, fetch),
      connect(fetch, batch),
      connect(batch, transform),
      connect(transform, rename),
      connect(rename, air),
    ],
    tags: ["etl", "airtable", "scheduled"],
  };
}

/** 4 · Daily briefing — 8am weekday Slack DM with weather + top news + AI summary. */
function buildDailyBriefing(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Weekdays @ 08:00", [80, 220], {
    cron: "0 0 8 * * 1-5",
    timezone: "America/Los_Angeles",
  });
  const weather = mkNode("weftlyflow.http_request", "Weather (open-meteo)", [320, 120], {
    method: "GET",
    url: "https://api.open-meteo.com/v1/forecast?latitude=37.77&longitude=-122.42&current=temperature_2m,weather_code",
  });
  const news = mkNode("weftlyflow.http_request", "Top HN stories", [320, 320], {
    method: "GET",
    url: "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=5",
  });
  const merge = mkNode("weftlyflow.merge", "Combine feeds", [560, 220], {
    mode: "merge_by_index",
  });
  const summarise = mkNode("weftlyflow.openai", "Write briefing", [820, 220], {
    model: "gpt-4o-mini",
    system_prompt:
      "You are a crisp morning briefing writer. Output exactly 4 lines: weather, top story, second story, motivational closer. No emojis in body.",
    user_prompt:
      "Weather: {{ $json.current.temperature_2m }}°C, code {{ $json.current.weather_code }}.\nTop stories: {{ $json.hits.map(h => h.title).join(' | ') }}",
    max_tokens: 250,
  });
  const post = mkNode("weftlyflow.slack", "DM briefing", [1080, 220], {
    operation: "postMessage",
    channel: "@me",
    text: "☀️ Morning brief — {{ $today }}\n\n{{ $json.choices[0].message.content }}",
  });
  return {
    name: "Daily briefing · Weather + news digest",
    nodes: [trigger, weather, news, merge, summarise, post],
    connections: [
      connect(trigger, weather),
      connect(trigger, news),
      connect(weather, merge),
      connect(news, merge),
      connect(merge, summarise),
      connect(summarise, post),
    ],
    tags: ["daily", "slack", "openai", "scheduled"],
  };
}

/** 5 · Lead capture — form webhook → Sheets + HubSpot + welcome email. */
function buildLeadCapture(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "Form submitted", [80, 220], {
    path: "lead-form",
    method: "POST",
  });
  const normalise = mkNode("weftlyflow.set", "Normalise fields", [320, 220], {
    values: {
      email: "={{ ($json.email || '').toLowerCase().trim() }}",
      full_name: "={{ $json.first_name + ' ' + $json.last_name }}",
      company: "={{ $json.company || 'Unknown' }}",
      source: "={{ $json.utm_source || 'direct' }}",
      submitted_at: "={{ $now.toISO() }}",
    },
  });
  const sheet = mkNode("weftlyflow.google_sheets", "Append to Sheet", [580, 100], {
    operation: "append_row",
    spreadsheet_id: "YOUR_SHEET_ID",
    range: "Leads!A:E",
    values: [
      "={{ $json.submitted_at }}",
      "={{ $json.full_name }}",
      "={{ $json.email }}",
      "={{ $json.company }}",
      "={{ $json.source }}",
    ],
  });
  const crm = mkNode("weftlyflow.hubspot", "Create contact", [580, 240], {
    operation: "create_contact",
    properties: {
      email: "={{ $json.email }}",
      firstname: "={{ $json.first_name }}",
      lastname: "={{ $json.last_name }}",
      company: "={{ $json.company }}",
      hs_lead_status: "NEW",
    },
  });
  const welcome = mkNode("weftlyflow.gmail", "Welcome email", [580, 380], {
    operation: "send",
    to: "={{ $json.email }}",
    subject: "Welcome, {{ $json.full_name }} 👋",
    body: "Hi {{ $json.full_name }},\n\nThanks for reaching out — we'll be in touch within one business day.\n\nCheers,\nThe Team",
  });
  return {
    name: "Lead capture · Form → Sheets + HubSpot + email",
    nodes: [hook, normalise, sheet, crm, welcome],
    connections: [
      connect(hook, normalise),
      connect(normalise, sheet),
      connect(normalise, crm),
      connect(normalise, welcome),
    ],
    tags: ["growth", "hubspot", "gmail", "sheets"],
  };
}

/** 6 · Weekly metrics report — Monday 9am Postgres-like query → exec summary → Slack. */
function buildWeeklyReport(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Mondays @ 09:00", [80, 220], {
    cron: "0 0 9 * * 1",
    timezone: "America/Los_Angeles",
  });
  const fetch = mkNode("weftlyflow.http_request", "Pull metrics", [320, 220], {
    method: "GET",
    url: "https://api.example.com/v1/metrics/weekly?end={{ $today }}",
  });
  const deltas = mkNode("weftlyflow.transform", "Compute deltas", [580, 220], {
    script:
      "item.signups_wow = ((item.signups - item.signups_prev) / Math.max(item.signups_prev, 1)) * 100;\n" +
      "item.revenue_wow = ((item.revenue - item.revenue_prev) / Math.max(item.revenue_prev, 1)) * 100;\n" +
      "item.churn_wow = item.churn - item.churn_prev;\nreturn item;",
  });
  const narrate = mkNode("weftlyflow.openai", "Exec narrative", [820, 220], {
    model: "gpt-4o-mini",
    system_prompt:
      "You write concise weekly KPI summaries for executives. Lead with the biggest mover. Use plain language. Max 4 bullets.",
    user_prompt:
      "Signups: {{ $json.signups }} ({{ $json.signups_wow }}% WoW)\nRevenue: ${{ $json.revenue }} ({{ $json.revenue_wow }}% WoW)\nChurn: {{ $json.churn }}%",
    max_tokens: 350,
  });
  const post = mkNode("weftlyflow.slack", "Post #leadership", [1080, 220], {
    operation: "postMessage",
    channel: "#leadership",
    text: "📊 Weekly KPIs — week ending {{ $today }}\n\n{{ $json.choices[0].message.content }}",
  });
  return {
    name: "Weekly metrics report · KPIs → exec summary",
    nodes: [trigger, fetch, deltas, narrate, post],
    connections: [
      connect(trigger, fetch),
      connect(fetch, deltas),
      connect(deltas, narrate),
      connect(narrate, post),
    ],
    tags: ["reporting", "openai", "slack", "scheduled"],
  };
}

// Templates · AI agent flows ----------------------------------------------

/** 7 · Email triage agent — poll Gmail → classify + draft with GPT → label & save draft. */
function buildEmailTriageAgent(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Every 15 minutes", [80, 220], {
    cron: "0 */15 * * * *",
  });
  const inbox = mkNode("weftlyflow.gmail", "List unread", [320, 220], {
    operation: "list_messages",
    query: "is:unread newer_than:1h",
    max_results: 25,
  });
  const batch = mkNode("weftlyflow.split_in_batches", "One by one", [560, 220], {
    batch_size: 1,
  });
  const classify = mkNode("weftlyflow.openai", "Classify + draft", [800, 220], {
    model: "gpt-4o-mini",
    system_prompt:
      "You classify emails into one of: URGENT, CUSTOMER, NEWSLETTER, PERSONAL, SPAM. " +
      "For URGENT and CUSTOMER emails, also draft a polite 3-sentence reply. " +
      "Output JSON: {category, confidence, draft_reply}.",
    user_prompt:
      "Subject: {{ $json.subject }}\nFrom: {{ $json.from }}\n\nBody:\n{{ $json.snippet }}",
    response_format: "json_object",
    max_tokens: 400,
  });
  const route = mkNode("weftlyflow.switch", "Route by class", [1040, 220], {
    rules: [
      { name: "urgent", condition: '={{ $json.category === "URGENT" }}' },
      { name: "customer", condition: '={{ $json.category === "CUSTOMER" }}' },
      { name: "spam", condition: '={{ $json.category === "SPAM" }}' },
    ],
    fallback: "archive",
  });
  const urgent = mkNode("weftlyflow.slack", "Ping #urgent", [1300, 60], {
    operation: "postMessage",
    channel: "#urgent-email",
    text: "🔥 Urgent: {{ $json.subject }} — {{ $json.from }}",
  });
  const draft = mkNode("weftlyflow.gmail", "Save reply draft", [1300, 200], {
    operation: "create_draft",
    to: "={{ $json.from }}",
    subject: "Re: {{ $json.subject }}",
    body: "={{ $json.draft_reply }}",
  });
  const trash = mkNode("weftlyflow.gmail", "Trash spam", [1300, 340], {
    operation: "modify_labels",
    message_id: "={{ $json.id }}",
    add_labels: ["TRASH"],
  });
  const archive = mkNode("weftlyflow.gmail", "Archive", [1300, 480], {
    operation: "modify_labels",
    message_id: "={{ $json.id }}",
    remove_labels: ["INBOX"],
  });
  return {
    name: "AI email triage agent · Classify + draft replies",
    nodes: [trigger, inbox, batch, classify, route, urgent, draft, trash, archive],
    connections: [
      connect(trigger, inbox),
      connect(inbox, batch),
      connect(batch, classify),
      connect(classify, route),
      connect(route, urgent, "urgent"),
      connect(route, draft, "customer"),
      connect(route, trash, "spam"),
      connect(route, archive, "archive"),
    ],
    tags: ["ai", "agent", "gmail", "scheduled"],
  };
}

/** 8 · Meeting notes agent — transcript webhook → Claude summary + actions → Notion + Slack. */
function buildMeetingNotesAgent(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "Transcript webhook", [80, 220], {
    path: "meeting-transcript",
    method: "POST",
  });
  const split = mkNode("weftlyflow.text_splitter", "Chunk transcript", [320, 220], {
    chunk_size: 6000,
    chunk_overlap: 300,
    input: "={{ $json.transcript }}",
  });
  const summary = mkNode("weftlyflow.anthropic", "Summarise + extract", [580, 220], {
    operation: "create_message",
    model: "claude-3-5-sonnet-latest",
    system:
      "You distil meeting transcripts. Output strict JSON: " +
      '{"title": string, "summary": string (3 bullets), "decisions": string[], "actions": [{"owner": string, "task": string, "due": string | null}]}. ' +
      "No prose outside JSON.",
    messages: '=[{"role":"user","content":"Transcript:\\n{{ $json.chunk }}"}]',
    max_tokens: 1200,
  });
  const shape = mkNode("weftlyflow.guard_schema_enforce", "Validate shape", [820, 220], {
    schema: {
      type: "object",
      required: ["title", "summary", "actions"],
      properties: {
        title: { type: "string" },
        summary: { type: "string" },
        decisions: { type: "array" },
        actions: { type: "array" },
      },
    },
  });
  const page = mkNode("weftlyflow.notion", "Create meeting page", [1080, 120], {
    operation: "createPage",
    database_id: "YOUR_MEETINGS_DB_ID",
    properties: {
      Name: "={{ $json.title }}",
      Date: "={{ $today }}",
    },
    content: "={{ $json.summary }}\n\nDecisions:\n{{ ($json.decisions || []).map(d => '• ' + d).join('\\n') }}\n\nActions:\n{{ ($json.actions || []).map(a => '• ' + a.owner + ': ' + a.task).join('\\n') }}",
  });
  const post = mkNode("weftlyflow.slack", "Share in #meetings", [1080, 320], {
    operation: "postMessage",
    channel: "#meetings",
    text: "📝 *{{ $json.title }}* — summary + {{ ($json.actions || []).length }} action items posted to Notion",
  });
  return {
    name: "Meeting notes agent · Transcript → Notion + Slack",
    nodes: [hook, split, summary, shape, page, post],
    connections: [
      connect(hook, split),
      connect(split, summary),
      connect(summary, shape),
      connect(shape, page),
      connect(shape, post),
    ],
    tags: ["ai", "agent", "anthropic", "notion"],
  };
}

/** 9 · Support auto-responder agent — ticket → RAG lookup → Claude draft → human review. */
function buildSupportAgent(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "New ticket", [80, 220], {
    path: "support-ticket",
    method: "POST",
  });
  const jailbreak = mkNode("weftlyflow.guard_jailbreak_detect", "Jailbreak guard", [320, 220]);
  const embed = mkNode("weftlyflow.embed_openai", "Embed question", [560, 220], {
    model: "text-embedding-3-small",
    input: "={{ $json.body }}",
  });
  const search = mkNode("weftlyflow.vector_qdrant", "Search KB", [800, 220], {
    operation: "query",
    collection: "support-kb",
    top_k: 5,
    vector: "={{ $json.embedding }}",
  });
  const draft = mkNode("weftlyflow.anthropic", "Draft reply", [1060, 220], {
    operation: "create_message",
    model: "claude-3-5-sonnet-latest",
    system:
      "You draft empathetic, accurate support replies using ONLY the provided KB snippets. " +
      "If the snippets don't cover the question, say so and hand off to a human. " +
      "Tone: warm, concise, specific. Never invent features.",
    messages:
      '=[{"role":"user","content":"Customer: {{ $json.from }}\\n\\nQuestion:\\n{{ $json.body }}\\n\\nKB snippets:\\n{{ $json.matches.map(m => m.text).join(\\"\\\\n---\\\\n\\") }}"}]',
    max_tokens: 700,
  });
  const redact = mkNode("weftlyflow.guard_pii_redact", "Redact PII", [1320, 220]);
  const review = mkNode("weftlyflow.slack", "#support-queue review", [1580, 220], {
    operation: "postMessage",
    channel: "#support-queue",
    text:
      "🎫 Ticket from {{ $json.from }}\n\n*Question:* {{ $json.body }}\n\n*Drafted reply (review before sending):*\n{{ $json.content[0].text }}",
  });
  return {
    name: "Support agent · Ticket → RAG → Claude draft → review",
    nodes: [hook, jailbreak, embed, search, draft, redact, review],
    connections: [
      connect(hook, jailbreak),
      connect(jailbreak, embed),
      connect(embed, search),
      connect(search, draft),
      connect(draft, redact),
      connect(redact, review),
    ],
    tags: ["ai", "agent", "rag", "anthropic", "support"],
  };
}

/** 10 · RAG chat assistant — flagship retrieval + reasoning chat. */
function buildRagAssistant(): WorkflowCreate {
  const chat = mkNode("weftlyflow.trigger_chat", "Chat input", [80, 200]);
  const guard = mkNode("weftlyflow.guard_jailbreak_detect", "Jailbreak guard", [320, 200]);
  const embed = mkNode("weftlyflow.embed_openai", "Embed query", [560, 200], {
    model: "text-embedding-3-small",
    input: "={{ $json.message }}",
  });
  const search = mkNode("weftlyflow.vector_qdrant", "Search KB", [800, 200], {
    operation: "query",
    collection: "knowledge-base",
    top_k: 6,
    vector: "={{ $json.embedding }}",
  });
  const memory = mkNode("weftlyflow.memory_window", "Last 6 turns", [800, 360], {
    k: 6,
    session_id: "={{ $json.session_id }}",
  });
  const llm = mkNode("weftlyflow.openai", "Answer with context", [1060, 260], {
    model: "gpt-4o",
    system_prompt:
      "You answer using ONLY the provided context. Cite the snippet id used. If unsure, say you don't know.",
    user_prompt:
      "Context:\n{{ $json.matches.map(m => m.text).join('\\n---\\n') }}\n\nQuestion: {{ $json.message }}",
    max_tokens: 800,
  });
  const schema = mkNode("weftlyflow.guard_schema_enforce", "Schema check", [1320, 260], {
    schema: { type: "object", required: ["answer"] },
  });
  const respond = mkNode("weftlyflow.chat_respond", "Send reply", [1560, 260]);
  return {
    name: "RAG assistant · Chat → Qdrant → GPT-4o",
    nodes: [chat, guard, embed, search, memory, llm, schema, respond],
    connections: [
      connect(chat, guard),
      connect(guard, embed),
      connect(embed, search),
      connect(chat, memory),
      connect(search, llm),
      connect(memory, llm),
      connect(llm, schema),
      connect(schema, respond),
    ],
    tags: ["ai", "agent", "rag", "qdrant", "openai"],
  };
}

// Templates · advanced professional --------------------------------------

/** 11 · Code review agent — GitHub PR → Claude structured review → inline comment. */
function buildCodeReviewAgent(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "GitHub PR event", [80, 220], {
    path: "github-pr",
    method: "POST",
  });
  const onlyRelevant = mkNode("weftlyflow.filter", "opened/synchronize", [320, 220], {
    condition: '={{ ["opened", "synchronize", "reopened"].includes($json.action) }}',
  });
  const diff = mkNode("weftlyflow.http_request", "Fetch PR diff", [560, 220], {
    method: "GET",
    url: "={{ $json.pull_request.diff_url }}",
    headers: { Accept: "application/vnd.github.v3.diff" },
  });
  const review = mkNode("weftlyflow.anthropic", "Claude code review", [820, 220], {
    operation: "create_message",
    model: "claude-3-5-sonnet-latest",
    system:
      "Senior engineer reviewing a GitHub PR diff. Output strict JSON only: " +
      '{"verdict":"approve"|"comment"|"request_changes","summary":string,"issues":[{"file":string,"line":number|null,"severity":"low"|"med"|"high","message":string,"suggestion":string}]}',
    messages: '=[{"role":"user","content":"PR: {{ $json.pull_request.title }}\\n\\nDiff:\\n{{ $json.body }}"}]',
    max_tokens: 2000,
  });
  const shape = mkNode("weftlyflow.guard_schema_enforce", "Validate review", [1080, 220], {
    schema: {
      type: "object",
      required: ["verdict", "summary", "issues"],
      properties: {
        verdict: { enum: ["approve", "comment", "request_changes"] },
        summary: { type: "string" },
        issues: { type: "array" },
      },
    },
  });
  const post = mkNode("weftlyflow.github", "Post PR review", [1340, 220], {
    operation: "create_review",
    owner: "={{ $json.repository.owner.login }}",
    repo: "={{ $json.repository.name }}",
    pull_number: "={{ $json.pull_request.number }}",
    body: "={{ $json.summary + '\\n\\n' + $json.issues.map(i => '• `' + i.file + (i.line ? ':' + i.line : '') + '` **' + i.severity.toUpperCase() + '** ' + i.message).join('\\n') }}",
    event: "={{ $json.verdict === 'approve' ? 'APPROVE' : $json.verdict === 'request_changes' ? 'REQUEST_CHANGES' : 'COMMENT' }}",
  });
  const nodes = [hook, onlyRelevant, diff, review, shape, post];
  return {
    name: "Code review agent · PR diff → Claude review",
    nodes,
    connections: linearConnect(nodes),
    tags: ["ai", "agent", "github", "claude"],
  };
}

/** 12 · Calendar prep briefing — 7am weekday meeting prep notes DM. */
function buildCalendarPrep(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Weekdays @ 07:00", [80, 220], {
    cron: "0 0 7 * * 1-5",
  });
  const list = mkNode("weftlyflow.gmail", "Today's invites", [320, 220], {
    operation: "list_messages",
    query: "from:(calendar-notification@google.com OR invite) newer_than:1d",
    max_results: 10,
  });
  const brief = mkNode("weftlyflow.openai", "Per-meeting prep", [580, 220], {
    model: "gpt-4o-mini",
    system_prompt:
      "Produce concise meeting prep notes. Strict JSON: {\"meetings\":[{\"title\":string,\"time\":string,\"attendees\":string[],\"agenda\":string,\"prep_points\":string[]}]}.",
    user_prompt: "Invites:\n{{ $json.messages.map(m => m.snippet).join('\\n\\n') }}",
    response_format: "json_object",
    max_tokens: 900,
  });
  const dm = mkNode("weftlyflow.slack", "DM briefing", [840, 220], {
    operation: "postMessage",
    channel: "@me",
    text: "📅 Today's meetings — {{ $today }}\n\n{{ $json.meetings.map(m => '*' + m.time + '* — ' + m.title + '\\n  → ' + m.prep_points.map(p => '• ' + p).join('\\n  ')).join('\\n\\n') }}",
  });
  const nodes = [trigger, list, brief, dm];
  return {
    name: "Calendar prep · Meeting briefings DM",
    nodes,
    connections: linearConnect(nodes),
    tags: ["ai", "gmail", "slack", "daily"],
  };
}

/** 13 · Social content repurposer — blog webhook → Claude → Twitter + LinkedIn. */
function buildContentRepurposer(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "New blog post", [80, 240], {
    path: "blog-published",
    method: "POST",
  });
  const fan = mkNode("weftlyflow.anthropic", "Repurpose content", [320, 240], {
    operation: "create_message",
    model: "claude-3-5-sonnet-latest",
    system:
      "You repurpose long-form blog content into social posts. Strict JSON only: " +
      '{"tweets":string[5],"linkedin":string,"hashtags":string[]}. ' +
      "Tweets under 260 chars; LinkedIn 500-900 chars with a hook and CTA.",
    messages: '=[{"role":"user","content":"Title: {{ $json.title }}\\n\\nBody:\\n{{ $json.content }}"}]',
    max_tokens: 1500,
  });
  const shape = mkNode("weftlyflow.guard_schema_enforce", "Validate JSON", [580, 240], {
    schema: {
      type: "object",
      required: ["tweets", "linkedin"],
      properties: {
        tweets: { type: "array", items: { type: "string" } },
        linkedin: { type: "string" },
        hashtags: { type: "array" },
      },
    },
  });
  const twitter = mkNode("weftlyflow.http_request", "Queue tweets (Buffer)", [840, 140], {
    method: "POST",
    url: "https://api.bufferapp.com/1/updates/create.json",
    headers: { "Content-Type": "application/json" },
    body: {
      profile_ids: ["YOUR_TWITTER_PROFILE_ID"],
      text: "={{ $json.tweets.join('\\n\\n---\\n\\n') }}",
    },
  });
  const linkedin = mkNode("weftlyflow.http_request", "Queue LinkedIn", [840, 340], {
    method: "POST",
    url: "https://api.bufferapp.com/1/updates/create.json",
    headers: { "Content-Type": "application/json" },
    body: {
      profile_ids: ["YOUR_LINKEDIN_PROFILE_ID"],
      text: "={{ $json.linkedin + '\\n\\n' + ($json.hashtags || []).map(h => '#' + h).join(' ') }}",
    },
  });
  return {
    name: "Content repurposer · Blog → Twitter + LinkedIn",
    nodes: [hook, fan, shape, twitter, linkedin],
    connections: [connect(hook, fan), connect(fan, shape), connect(shape, twitter), connect(shape, linkedin)],
    tags: ["ai", "social", "anthropic", "marketing"],
  };
}

/** 14 · Competitor price monitor — daily scrape → diff → Slack alert on change. */
function buildPriceMonitor(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Daily @ 06:00", [80, 220], {
    cron: "0 0 6 * * *",
  });
  const scrape = mkNode("weftlyflow.http_request", "Fetch product page", [320, 220], {
    method: "GET",
    url: "https://competitor.example.com/products/flagship",
  });
  const parse = mkNode("weftlyflow.html_parse", "Extract price", [560, 220], {
    source_path: "body",
    extractions: [
      { key: "price", selector: '[data-testid="price"]', attr: "text" },
      { key: "availability", selector: '[data-testid="stock"]', attr: "text" },
    ],
  });
  const diff = mkNode("weftlyflow.transform", "Compare to yesterday", [820, 220], {
    script:
      "const prev = $ctx.state.get('last_price') || null;\n" +
      "item.previous = prev;\n" +
      "item.changed = prev !== null && prev !== item.price;\n" +
      "$ctx.state.set('last_price', item.price);\n" +
      "return item;",
  });
  const changed = mkNode("weftlyflow.if", "Price changed?", [1080, 220], {
    condition: "={{ $json.changed === true }}",
  });
  const alert = mkNode("weftlyflow.slack", "Alert #pricing", [1340, 140], {
    operation: "postMessage",
    channel: "#pricing",
    text: "💲 Competitor price changed: *{{ $json.previous }} → {{ $json.price }}* · stock {{ $json.availability }}",
  });
  const noop = mkNode("weftlyflow.no_op", "No change", [1340, 300]);
  return {
    name: "Competitor price monitor · Scrape → diff → alert",
    nodes: [trigger, scrape, parse, diff, changed, alert, noop],
    connections: [
      connect(trigger, scrape),
      connect(scrape, parse),
      connect(parse, diff),
      connect(diff, changed),
      connect(changed, alert, "true"),
      connect(changed, noop, "false"),
    ],
    tags: ["monitoring", "scraping", "slack", "scheduled"],
  };
}

/** 15 · Customer feedback analyzer — sentiment + category JSON → route. */
function buildFeedbackAnalyzer(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "Intercom message", [80, 260], {
    path: "intercom-feedback",
    method: "POST",
  });
  const classify = mkNode("weftlyflow.openai", "Sentiment + category", [320, 260], {
    model: "gpt-4o-mini",
    system_prompt:
      "Analyse customer feedback. Strict JSON: " +
      '{"sentiment":"positive"|"neutral"|"negative","score":number,"category":"bug"|"feature_request"|"praise"|"billing"|"other","summary":string,"urgency":"low"|"med"|"high"}.',
    user_prompt: "Feedback from {{ $json.user.email }}:\n{{ $json.message.body }}",
    response_format: "json_object",
    max_tokens: 300,
  });
  const shape = mkNode("weftlyflow.guard_schema_enforce", "Validate analysis", [580, 260], {
    schema: {
      type: "object",
      required: ["sentiment", "category", "urgency"],
      properties: { sentiment: { enum: ["positive", "neutral", "negative"] } },
    },
  });
  const router = mkNode("weftlyflow.switch", "Route by sentiment", [840, 260], {
    rules: [
      { name: "angry", condition: '={{ $json.sentiment === "negative" && $json.urgency === "high" }}' },
      { name: "positive", condition: '={{ $json.sentiment === "positive" }}' },
    ],
    fallback: "review",
  });
  const alert = mkNode("weftlyflow.slack", "Alert CS lead", [1100, 120], {
    operation: "postMessage",
    channel: "#cs-urgent",
    text: "🔥 Urgent negative feedback — {{ $json.category }}: {{ $json.summary }}",
  });
  const praise = mkNode("weftlyflow.notion", "Log to wins", [1100, 260], {
    operation: "createPage",
    database_id: "YOUR_WINS_DB_ID",
    properties: { Name: "={{ $json.summary }}", Category: "={{ $json.category }}" },
  });
  const backlog = mkNode("weftlyflow.notion", "Log to feedback DB", [1100, 400], {
    operation: "createPage",
    database_id: "YOUR_FEEDBACK_DB_ID",
    properties: {
      Name: "={{ $json.summary }}",
      Sentiment: "={{ $json.sentiment }}",
      Category: "={{ $json.category }}",
    },
  });
  return {
    name: "Feedback analyzer · Sentiment JSON → route",
    nodes: [hook, classify, shape, router, alert, praise, backlog],
    connections: [
      connect(hook, classify),
      connect(classify, shape),
      connect(shape, router),
      connect(router, alert, "angry"),
      connect(router, praise, "positive"),
      connect(router, backlog, "review"),
    ],
    tags: ["ai", "cs", "notion", "slack"],
  };
}

/** 16 · Churn risk predictor — daily event pull → score → hot-list high-risk. */
function buildChurnPredictor(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Daily @ 04:00", [80, 220], {
    cron: "0 0 4 * * *",
  });
  const pull = mkNode("weftlyflow.http_request", "User events", [320, 220], {
    method: "GET",
    url: "https://api.example.com/v1/events?window=30d",
  });
  const batch = mkNode("weftlyflow.split_in_batches", "Per user", [560, 220], {
    batch_size: 1,
  });
  const score = mkNode("weftlyflow.transform", "Score risk", [800, 220], {
    script:
      "const wEmail = Math.max(0, 14 - (item.days_since_last_login || 0)) / 14;\n" +
      "const wUsage = Math.min(1, (item.sessions_7d || 0) / 5);\n" +
      "const wPayment = item.payment_failed_30d ? 0 : 1;\n" +
      "item.risk = Math.round((1 - (wEmail * 0.4 + wUsage * 0.4 + wPayment * 0.2)) * 100);\n" +
      "item.tier = item.risk > 70 ? 'high' : item.risk > 40 ? 'med' : 'low';\n" +
      "return item;",
  });
  const highOnly = mkNode("weftlyflow.filter", "Risk > 70", [1040, 220], {
    condition: "={{ $json.risk > 70 }}",
  });
  const tag = mkNode("weftlyflow.hubspot", "Tag in CRM", [1280, 120], {
    operation: "update_contact",
    contact_id: "={{ $json.hubspot_id }}",
    properties: { churn_risk: "={{ $json.risk }}", churn_tier: "high" },
  });
  const notify = mkNode("weftlyflow.slack", "Ping CSM", [1280, 320], {
    operation: "postMessage",
    channel: "#cs-retention",
    text: "⚠️ Churn risk {{ $json.risk }}/100 — {{ $json.email }} ({{ $json.plan }})",
  });
  return {
    name: "Churn risk predictor · Score users → hot-list",
    nodes: [trigger, pull, batch, score, highOnly, tag, notify],
    connections: [
      connect(trigger, pull),
      connect(pull, batch),
      connect(batch, score),
      connect(score, highOnly),
      connect(highOnly, tag),
      connect(highOnly, notify),
    ],
    tags: ["data", "hubspot", "retention", "scheduled"],
  };
}

/** 17 · Expense receipts OCR — Gmail receipts → Claude extract → Sheets ledger. */
function buildExpenseOcr(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Hourly", [80, 220], {
    cron: "0 0 * * * *",
  });
  const inbox = mkNode("weftlyflow.gmail", "List receipts", [320, 220], {
    operation: "list_messages",
    query: 'subject:(receipt OR invoice OR "order confirmation") newer_than:1h',
    max_results: 20,
  });
  const batch = mkNode("weftlyflow.split_in_batches", "One at a time", [560, 220], {
    batch_size: 1,
  });
  const extract = mkNode("weftlyflow.anthropic", "Extract JSON", [800, 220], {
    operation: "create_message",
    model: "claude-3-5-sonnet-latest",
    system:
      'Extract receipt details. Strict JSON only: {"merchant":string,"amount":number,"currency":string,"date":"YYYY-MM-DD","category":"meals"|"travel"|"software"|"office"|"other","tax":number|null}.',
    messages: '=[{"role":"user","content":"Email body:\\n{{ $json.snippet }}\\n\\nSubject: {{ $json.subject }}"}]',
    max_tokens: 400,
  });
  const shape = mkNode("weftlyflow.guard_schema_enforce", "Validate", [1040, 220], {
    schema: {
      type: "object",
      required: ["merchant", "amount", "currency", "date"],
      properties: { amount: { type: "number" }, category: { type: "string" } },
    },
  });
  const sheet = mkNode("weftlyflow.google_sheets", "Append ledger row", [1280, 220], {
    operation: "append_row",
    spreadsheet_id: "YOUR_LEDGER_SHEET_ID",
    range: "Expenses!A:F",
    values: [
      "={{ $json.date }}",
      "={{ $json.merchant }}",
      "={{ $json.amount }}",
      "={{ $json.currency }}",
      "={{ $json.category }}",
      "={{ $json.tax }}",
    ],
  });
  const nodes = [trigger, inbox, batch, extract, shape, sheet];
  return {
    name: "Expense OCR · Receipts → structured ledger",
    nodes,
    connections: linearConnect(nodes),
    tags: ["ai", "finance", "gmail", "sheets"],
  };
}

/** 18 · Weekly SEO audit — Lighthouse → GPT interpretation → Notion report. */
function buildSeoAudit(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Mondays @ 06:00", [80, 220], {
    cron: "0 0 6 * * 1",
  });
  const audit = mkNode("weftlyflow.http_request", "Lighthouse API", [320, 220], {
    method: "GET",
    url: "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https%3A%2F%2Fyoursite.com&strategy=mobile&category=seo&category=performance&category=accessibility",
  });
  const summarise = mkNode("weftlyflow.openai", "Interpret scores", [580, 220], {
    model: "gpt-4o-mini",
    system_prompt:
      "Interpret a Lighthouse audit for a non-technical stakeholder. Strict JSON: " +
      '{"overall_score":number,"perf":number,"seo":number,"a11y":number,"top_issues":[{"issue":string,"impact":"low"|"med"|"high","fix":string}],"quick_wins":string[]}.',
    user_prompt: "Lighthouse result:\n{{ JSON.stringify($json.lighthouseResult.categories) }}",
    response_format: "json_object",
    max_tokens: 1200,
  });
  const shape = mkNode("weftlyflow.guard_schema_enforce", "Validate report", [840, 220], {
    schema: { type: "object", required: ["overall_score", "top_issues"] },
  });
  const page = mkNode("weftlyflow.notion", "Create report page", [1100, 120], {
    operation: "createPage",
    database_id: "YOUR_SEO_DB_ID",
    properties: {
      Name: "={{ 'SEO audit · ' + $today }}",
      Score: "={{ $json.overall_score }}",
    },
    content: "={{ $json.top_issues.map(i => '• **' + i.impact.toUpperCase() + '** ' + i.issue + ' → ' + i.fix).join('\\n') + '\\n\\nQuick wins:\\n' + $json.quick_wins.map(w => '• ' + w).join('\\n') }}",
  });
  const slack = mkNode("weftlyflow.slack", "Post to #growth", [1100, 320], {
    operation: "postMessage",
    channel: "#growth",
    text: "🧭 Weekly SEO audit — overall {{ $json.overall_score }}/100 · {{ $json.top_issues.length }} issues flagged",
  });
  return {
    name: "Weekly SEO audit · Lighthouse → report",
    nodes: [trigger, audit, summarise, shape, page, slack],
    connections: [
      connect(trigger, audit),
      connect(audit, summarise),
      connect(summarise, shape),
      connect(shape, page),
      connect(shape, slack),
    ],
    tags: ["seo", "openai", "notion", "scheduled"],
  };
}

/** 19 · Sales pipeline digest — daily HubSpot rollup → exec narrative → Slack. */
function buildPipelineDigest(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Daily @ 08:30", [80, 220], {
    cron: "0 30 8 * * 1-5",
  });
  const deals = mkNode("weftlyflow.hubspot", "List open deals", [320, 220], {
    operation: "search_deals",
    filter_groups: [
      { filters: [{ propertyName: "dealstage", operator: "NOT_IN", values: ["closedwon", "closedlost"] }] },
    ],
    limit: 100,
  });
  const roll = mkNode("weftlyflow.transform", "Aggregate by stage", [560, 220], {
    script:
      "const by = {};\n" +
      "for (const d of item.results || []) {\n" +
      "  const s = d.properties.dealstage || 'unknown';\n" +
      "  by[s] = by[s] || { count: 0, value: 0 };\n" +
      "  by[s].count += 1;\n" +
      "  by[s].value += Number(d.properties.amount || 0);\n" +
      "}\n" +
      "item.by_stage = by;\n" +
      "item.total_value = Object.values(by).reduce((a, b) => a + b.value, 0);\n" +
      "return item;",
  });
  const narrate = mkNode("weftlyflow.openai", "Exec narrative", [820, 220], {
    model: "gpt-4o-mini",
    system_prompt:
      "You summarise the sales pipeline for a daily exec stand-up. Strict JSON: " +
      '{"headline":string,"total_value_usd":number,"stages":[{"name":string,"count":number,"value":number}],"focus":string[]}.',
    user_prompt: "Rollup:\n{{ JSON.stringify($json.by_stage) }}\n\nTotal: {{ $json.total_value }}",
    response_format: "json_object",
    max_tokens: 500,
  });
  const post = mkNode("weftlyflow.slack", "Post #sales-daily", [1080, 220], {
    operation: "postMessage",
    channel: "#sales-daily",
    text: "💼 *{{ $json.headline }}* — Total pipeline: ${{ $json.total_value_usd }}\n\n{{ $json.stages.map(s => '• ' + s.name + ': ' + s.count + ' deals · $' + s.value).join('\\n') }}\n\n*Today's focus:* {{ $json.focus.join(', ') }}",
  });
  const nodes = [trigger, deals, roll, narrate, post];
  return {
    name: "Sales pipeline digest · HubSpot → exec Slack",
    nodes,
    connections: linearConnect(nodes),
    tags: ["sales", "hubspot", "openai", "daily"],
  };
}

/** 20 · Incident postmortem drafter — PagerDuty → logs → Claude 5-section draft. */
function buildPostmortemDrafter(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "PagerDuty resolved", [80, 220], {
    path: "pd-postmortem",
    method: "POST",
  });
  const onlyResolved = mkNode("weftlyflow.filter", "event=resolved", [320, 220], {
    condition: '={{ $json.event === "incident.resolved" }}',
  });
  const logs = mkNode("weftlyflow.http_request", "Fetch incident logs", [560, 220], {
    method: "GET",
    url: "https://api.example.com/v1/logs?incident={{ $json.incident.id }}&window=2h",
  });
  const draft = mkNode("weftlyflow.anthropic", "Draft postmortem", [820, 220], {
    operation: "create_message",
    model: "claude-3-5-sonnet-latest",
    system:
      "Draft a blameless incident postmortem. Strict JSON: " +
      '{"title":string,"summary":string,"timeline":[{"t":string,"event":string}],"root_cause":string,"impact":string,"action_items":[{"owner":string,"action":string,"due":string}]}.',
    messages: '=[{"role":"user","content":"Incident: {{ $json.incident.title }}\\nSeverity: {{ $json.incident.urgency }}\\n\\nLogs:\\n{{ $json.body }}"}]',
    max_tokens: 2500,
  });
  const shape = mkNode("weftlyflow.guard_schema_enforce", "Validate draft", [1080, 220], {
    schema: { type: "object", required: ["title", "summary", "timeline", "root_cause", "action_items"] },
  });
  const page = mkNode("weftlyflow.notion", "Create postmortem page", [1340, 120], {
    operation: "createPage",
    database_id: "YOUR_POSTMORTEMS_DB_ID",
    properties: { Name: "={{ $json.title }}", Date: "={{ $today }}" },
    content:
      "={{ $json.summary + '\\n\\n## Timeline\\n' + $json.timeline.map(t => '- **' + t.t + '** — ' + t.event).join('\\n') + '\\n\\n## Root cause\\n' + $json.root_cause + '\\n\\n## Action items\\n' + $json.action_items.map(a => '- [ ] ' + a.owner + ': ' + a.action + ' (due ' + a.due + ')').join('\\n') }}",
  });
  const review = mkNode("weftlyflow.slack", "Ping #sre-review", [1340, 320], {
    operation: "postMessage",
    channel: "#sre-review",
    text: "🩹 Postmortem drafted — *{{ $json.title }}* — {{ $json.action_items.length }} action items for review",
  });
  return {
    name: "Incident postmortem drafter · PD → Claude → Notion",
    nodes: [hook, onlyResolved, logs, draft, shape, page, review],
    connections: [
      connect(hook, onlyResolved),
      connect(onlyResolved, logs),
      connect(logs, draft),
      connect(draft, shape),
      connect(shape, page),
      connect(shape, review),
    ],
    tags: ["sre", "anthropic", "notion", "postmortem"],
  };
}

/** 21 · Smart lead scoring — HubSpot webhook → Clearbit enrich → GPT score → update. */
function buildLeadScoring(): WorkflowCreate {
  const hook = mkNode("weftlyflow.webhook_trigger", "HubSpot new contact", [80, 240], {
    path: "hubspot-contact",
    method: "POST",
  });
  const enrich = mkNode("weftlyflow.http_request", "Clearbit enrich", [320, 240], {
    method: "GET",
    url: "https://person.clearbit.com/v2/combined/find?email={{ $json.email }}",
  });
  const score = mkNode("weftlyflow.openai", "Score 0-100", [580, 240], {
    model: "gpt-4o-mini",
    system_prompt:
      "ICP scorer for a SaaS product targeting 50-500 seat mid-market. Strict JSON: " +
      '{"score":number,"tier":"A"|"B"|"C","reasoning":string,"signals":string[]}.',
    user_prompt: "Contact:\n{{ JSON.stringify($json) }}",
    response_format: "json_object",
    max_tokens: 350,
  });
  const shape = mkNode("weftlyflow.guard_schema_enforce", "Validate score", [840, 240], {
    schema: {
      type: "object",
      required: ["score", "tier"],
      properties: { score: { type: "number" }, tier: { enum: ["A", "B", "C"] } },
    },
  });
  const update = mkNode("weftlyflow.hubspot", "Update score in CRM", [1100, 140], {
    operation: "update_contact",
    contact_id: "={{ $json.hubspot_id }}",
    properties: {
      lead_score: "={{ $json.score }}",
      lead_tier: "={{ $json.tier }}",
    },
  });
  const hot = mkNode("weftlyflow.if", "Tier A?", [1100, 340], {
    condition: '={{ $json.tier === "A" }}',
  });
  const alert = mkNode("weftlyflow.slack", "Alert AE", [1360, 260], {
    operation: "postMessage",
    channel: "#sales-hot",
    text: "🔥 Tier A lead — {{ $json.email }} · score {{ $json.score }}\n{{ $json.reasoning }}",
  });
  const cold = mkNode("weftlyflow.no_op", "Nurture track", [1360, 440]);
  return {
    name: "Smart lead scoring · Enrich → GPT → tier",
    nodes: [hook, enrich, score, shape, update, hot, alert, cold],
    connections: [
      connect(hook, enrich),
      connect(enrich, score),
      connect(score, shape),
      connect(shape, update),
      connect(shape, hot),
      connect(hot, alert, "true"),
      connect(hot, cold, "false"),
    ],
    tags: ["ai", "sales", "hubspot", "scoring"],
  };
}

/** 22 · Daily trend summariser — Reddit/news search → GPT themes → #marketing. */
function buildTrendSummariser(): WorkflowCreate {
  const trigger = mkNode("weftlyflow.schedule_trigger", "Weekdays @ 08:30", [80, 220], {
    cron: "0 30 8 * * 1-5",
  });
  const reddit = mkNode("weftlyflow.reddit", "Top posts in niche", [320, 120], {
    operation: "search",
    subreddit: "SaaS",
    time: "day",
    limit: 25,
  });
  const news = mkNode("weftlyflow.http_request", "Industry news", [320, 320], {
    method: "GET",
    url: "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=saas&numericFilters=created_at_i%3E{{ Math.floor(($now.toMillis() - 86400000) / 1000) }}",
  });
  const merge = mkNode("weftlyflow.merge", "Combine sources", [580, 220], {
    mode: "append",
  });
  const themes = mkNode("weftlyflow.openai", "Extract themes", [840, 220], {
    model: "gpt-4o-mini",
    system_prompt:
      "Identify the 3-5 strongest content themes emerging today. Strict JSON: " +
      '{"date":string,"themes":[{"theme":string,"why_it_matters":string,"sources":string[]}],"opportunity":string}.',
    user_prompt: "Items:\n{{ JSON.stringify($json.slice(0, 40)) }}",
    response_format: "json_object",
    max_tokens: 900,
  });
  const post = mkNode("weftlyflow.slack", "Post #marketing", [1100, 220], {
    operation: "postMessage",
    channel: "#marketing",
    text: "📈 Today's themes — {{ $json.date }}\n\n{{ $json.themes.map(t => '*' + t.theme + '* — ' + t.why_it_matters).join('\\n') }}\n\n*Opportunity:* {{ $json.opportunity }}",
  });
  return {
    name: "Trend summariser · Reddit + HN → daily themes",
    nodes: [trigger, reddit, news, merge, themes, post],
    connections: [
      connect(trigger, reddit),
      connect(trigger, news),
      connect(reddit, merge),
      connect(news, merge),
      connect(merge, themes),
      connect(themes, post),
    ],
    tags: ["growth", "reddit", "openai", "daily"],
  };
}

// Catalog ------------------------------------------------------------------

export const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  // — Daily utility —
  {
    id: "uptime-guard",
    name: "Uptime guard",
    description:
      "Pings an endpoint every 5 minutes and pages #incidents on Slack when the status isn't 200.",
    category: "DevOps",
    tone: "amber",
    stack: ["schedule", "HTTP", "if", "Slack"],
    icon: "Siren",
    build: buildUptimeGuard,
  },
  {
    id: "daily-briefing",
    name: "Daily morning briefing",
    description:
      "8am weekday Slack DM with weather, top 5 HN stories, and a GPT-written 4-line exec brief.",
    category: "Growth",
    tone: "amber",
    stack: ["schedule", "HTTP × 2", "merge", "OpenAI", "Slack"],
    icon: "Sunrise",
    build: buildDailyBriefing,
  },
  {
    id: "lead-capture",
    name: "Lead capture (form → CRM + email)",
    description:
      "Form webhook normalises fields, appends to Google Sheets, creates HubSpot contact, and sends a Gmail welcome.",
    category: "Growth",
    tone: "green",
    stack: ["webhook", "Set", "Sheets", "HubSpot", "Gmail"],
    icon: "ClipboardList",
    build: buildLeadCapture,
  },
  {
    id: "weekly-report",
    name: "Weekly metrics report",
    description:
      "Every Monday 9am: fetch KPIs, compute WoW deltas, GPT-written exec narrative, post to #leadership.",
    category: "Data",
    tone: "blue",
    stack: ["schedule", "HTTP", "transform", "OpenAI", "Slack"],
    icon: "BarChart3",
    build: buildWeeklyReport,
  },
  {
    id: "stripe-slack",
    name: "Stripe → Slack notifier",
    description:
      "Webhook ingests Stripe checkouts, shapes the payload, and fans out to #sales-vip vs #orders based on cart size.",
    category: "Notifications",
    tone: "blue",
    stack: ["webhook", "Set", "if", "Slack"],
    icon: "ShoppingBag",
    build: buildOrderNotifier,
  },
  {
    id: "etl-airtable",
    name: "Hourly ETL → Airtable",
    description:
      "Pulls orders every hour, batches in 50s, normalises the shape, renames keys, and upserts into Airtable.",
    category: "Data",
    tone: "teal",
    stack: ["schedule", "HTTP", "batch", "transform", "Airtable"],
    icon: "Database",
    build: buildEtl,
  },
  // — Popular AI agent flows —
  {
    id: "email-triage-agent",
    name: "AI email triage agent",
    description:
      "Every 15 min: classifies unread Gmail (URGENT · CUSTOMER · SPAM · ARCHIVE), drafts replies for the ones that matter, and routes the rest.",
    category: "AI",
    tone: "purple",
    stack: ["schedule", "Gmail", "OpenAI", "switch", "draft + archive"],
    icon: "Mail",
    build: buildEmailTriageAgent,
  },
  {
    id: "meeting-notes-agent",
    name: "AI meeting notes agent",
    description:
      "Transcript webhook → Claude summarises + extracts decisions & action items → Notion page + Slack post.",
    category: "AI",
    tone: "teal",
    stack: ["webhook", "splitter", "Claude", "schema guard", "Notion", "Slack"],
    icon: "FileText",
    build: buildMeetingNotesAgent,
  },
  {
    id: "support-agent",
    name: "AI support auto-responder",
    description:
      "Ticket webhook → jailbreak guard → KB retrieval (Qdrant) → Claude drafts empathetic reply → PII redact → #support-queue for human review.",
    category: "Support",
    tone: "pink",
    stack: ["webhook", "guards", "embeddings", "Qdrant", "Claude", "Slack"],
    icon: "LifeBuoy",
    build: buildSupportAgent,
  },
  {
    id: "rag-assistant",
    name: "RAG chat assistant",
    description:
      "Chat trigger with jailbreak guard, embedding → Qdrant retrieval, sliding-window memory, GPT-4o answer + schema guard.",
    category: "AI",
    tone: "pink",
    stack: ["chat", "guard", "embeddings", "Qdrant", "GPT-4o", "memory"],
    icon: "Bot",
    build: buildRagAssistant,
  },
  // — Advanced professional —
  {
    id: "code-review-agent",
    name: "AI code review agent",
    description:
      "GitHub PR webhook → fetches diff → Claude 3.5 Sonnet returns a structured review (verdict + per-file issues) → posts as a GitHub PR review.",
    category: "DevOps",
    tone: "purple",
    stack: ["webhook", "filter", "HTTP", "Claude JSON", "schema guard", "GitHub review"],
    icon: "Github",
    build: buildCodeReviewAgent,
  },
  {
    id: "calendar-prep",
    name: "Calendar prep briefing",
    description:
      "Weekdays 7am: pulls today's meeting invites from Gmail → GPT writes prep notes (title, attendees, agenda, talking points) → Slack DM.",
    category: "Growth",
    tone: "teal",
    stack: ["schedule", "Gmail", "OpenAI JSON", "Slack DM"],
    icon: "CalendarDays",
    build: buildCalendarPrep,
  },
  {
    id: "content-repurposer",
    name: "Social content repurposer",
    description:
      "Publish a blog → Claude turns it into 5 tweets + a LinkedIn post with hashtags → queues both via Buffer. JSON-validated output.",
    category: "Growth",
    tone: "pink",
    stack: ["webhook", "Claude JSON", "schema guard", "Buffer × 2 parallel"],
    icon: "Rocket",
    build: buildContentRepurposer,
  },
  {
    id: "price-monitor",
    name: "Competitor price monitor",
    description:
      "Daily scrape of a competitor page → HTML parse → diff against yesterday → Slack alert on price change, no-op otherwise.",
    category: "Data",
    tone: "amber",
    stack: ["schedule", "HTTP", "HTML parse", "transform", "if", "Slack"],
    icon: "TrendingUp",
    build: buildPriceMonitor,
  },
  {
    id: "feedback-analyzer",
    name: "Customer feedback analyzer",
    description:
      "Intercom webhook → GPT returns sentiment + category JSON → schema guard → switch fans out to #cs-urgent / wins DB / feedback DB.",
    category: "Support",
    tone: "blue",
    stack: ["webhook", "OpenAI JSON", "schema guard", "switch", "Slack + Notion × 2"],
    icon: "MessageSquare",
    build: buildFeedbackAnalyzer,
  },
  {
    id: "churn-predictor",
    name: "Churn risk predictor",
    description:
      "Daily: fetch user events → transform computes risk score (login + usage + payment) → filter high-risk → HubSpot tag + CSM ping.",
    category: "Data",
    tone: "purple",
    stack: ["schedule", "HTTP", "batch", "transform", "filter", "HubSpot + Slack"],
    icon: "AlertTriangle",
    build: buildChurnPredictor,
  },
  {
    id: "expense-ocr",
    name: "Expense receipts OCR",
    description:
      "Hourly: Gmail search for receipts → Claude extracts {merchant, amount, currency, date, category} → schema guard → Google Sheets ledger.",
    category: "Data",
    tone: "teal",
    stack: ["schedule", "Gmail", "Claude JSON", "schema guard", "Sheets"],
    icon: "Receipt",
    build: buildExpenseOcr,
  },
  {
    id: "seo-audit",
    name: "Weekly SEO audit",
    description:
      "Monday 6am: Google PageSpeed/Lighthouse run → GPT interprets scores + top issues + quick wins → Notion report + Slack #growth ping.",
    category: "Data",
    tone: "green",
    stack: ["schedule", "Lighthouse API", "OpenAI JSON", "schema guard", "Notion + Slack"],
    icon: "Globe",
    build: buildSeoAudit,
  },
  {
    id: "pipeline-digest",
    name: "Sales pipeline digest",
    description:
      "Weekday 8:30am: HubSpot open-deal query → aggregate by stage → GPT writes exec headline + stage rollup → #sales-daily Slack.",
    category: "Data",
    tone: "blue",
    stack: ["schedule", "HubSpot", "transform", "OpenAI JSON", "Slack"],
    icon: "DollarSign",
    build: buildPipelineDigest,
  },
  {
    id: "postmortem-drafter",
    name: "Incident postmortem drafter",
    description:
      "PagerDuty resolved webhook → fetch logs → Claude drafts 5-section postmortem (summary, timeline, root cause, impact, actions) → Notion + SRE review ping.",
    category: "DevOps",
    tone: "pink",
    stack: ["webhook", "filter", "HTTP", "Claude JSON", "schema guard", "Notion + Slack"],
    icon: "AlertOctagon",
    build: buildPostmortemDrafter,
  },
  {
    id: "lead-scoring",
    name: "Smart lead scoring",
    description:
      "HubSpot new-contact webhook → Clearbit enrichment → GPT scores 0-100 with A/B/C tier + reasoning → HubSpot update → tier-A gets a hot-lead Slack ping.",
    category: "Growth",
    tone: "amber",
    stack: ["webhook", "Clearbit HTTP", "OpenAI JSON", "schema guard", "HubSpot + if"],
    icon: "Target",
    build: buildLeadScoring,
  },
  {
    id: "trend-summariser",
    name: "Daily trend summariser",
    description:
      "Weekdays 8:30am: Reddit top posts + HN search merge → GPT extracts 3-5 themes + opportunity call-out → #marketing Slack briefing.",
    category: "Growth",
    tone: "purple",
    stack: ["schedule", "Reddit", "HTTP", "merge", "OpenAI JSON", "Slack"],
    icon: "Hash",
    build: buildTrendSummariser,
  },
];
