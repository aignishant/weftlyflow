// Field-example generator — derives placeholders, example values, and
// quick-insert suggestion chips for node parameters. Nodes can ship with
// their own placeholder/description, but anything left blank is augmented
// here based on property name + type heuristics. The goal is that every
// field a user sees carries either an `e.g.` hint or a set of tappable
// examples, so the form is self-teaching.

import type { NodeProperty } from "@/types/api";

export interface FieldHelp {
  /** Best-effort placeholder to show in the input. */
  placeholder: string;
  /** Short "e.g." sample value rendered below the field. */
  example: string | null;
  /** Quick-insert chips — clicking one fills the field. */
  suggestions: string[];
  /** Longer-form helpful tip (rendered on hover/expand). */
  tip: string | null;
}

interface Rule {
  /** Match the property name (lowercased) — either substring or regex. */
  test: RegExp;
  placeholder?: string;
  example?: string;
  suggestions?: string[];
  tip?: string;
}

// Order matters — first match wins. Keep specific patterns above generic
// ones (e.g. "api_key" before "key").
const NAME_RULES: Rule[] = [
  {
    test: /^url$|endpoint|webhook.?url|base.?url/i,
    placeholder: "https://api.example.com/v1/users",
    example: "https://api.github.com/repos/owner/repo",
    suggestions: [
      "https://api.example.com/v1/resource",
      "https://hooks.slack.com/services/XXX",
      "={{ $json.url }}",
    ],
    tip: "Any valid URL. Use {{ $json.fieldName }} to interpolate from the incoming item.",
  },
  {
    test: /method$/i,
    placeholder: "GET",
    example: "POST",
    suggestions: ["GET", "POST", "PUT", "PATCH", "DELETE"],
    tip: "HTTP verb. GET for reads, POST for creates, PATCH for partial updates.",
  },
  {
    test: /email/i,
    placeholder: "you@company.com",
    example: "alerts@acme.io",
    suggestions: ["{{ $json.email }}", "team@example.com"],
    tip: "A well-formed email address. Expressions with {{ $json.* }} work here.",
  },
  {
    test: /phone|msisdn|whatsapp/i,
    placeholder: "+14155552671",
    example: "+14155552671",
    suggestions: ["{{ $json.phone }}", "+14155552671"],
    tip: "E.164 format — country code first, no spaces.",
  },
  {
    test: /api.?key|secret|token|bearer/i,
    placeholder: "sk_live_••••••••••••",
    example: "stored securely via a credential",
    suggestions: [],
    tip: "Paste the raw value. It's masked here and encrypted at rest. Prefer credentials over inline values when possible.",
  },
  {
    test: /channel|room/i,
    placeholder: "#general",
    example: "#incidents",
    suggestions: ["#general", "#alerts", "{{ $json.channel }}"],
    tip: "Slack-style channel name, or an ID if your integration requires it.",
  },
  {
    test: /user.?name|login|handle/i,
    placeholder: "octocat",
    example: "octocat",
    suggestions: ["{{ $json.username }}", "admin", "octocat"],
  },
  {
    test: /password|passwd/i,
    placeholder: "••••••••",
    suggestions: [],
    tip: "Masked. Prefer storing in a credential over pasting inline.",
  },
  {
    test: /query|q$|search|keyword/i,
    placeholder: "weftlyflow is:open",
    example: 'subject:"urgent" is:unread',
    suggestions: ["is:open", "is:closed", "{{ $json.query }}"],
  },
  {
    test: /subject|title|summary/i,
    placeholder: "Order #{{ $json.id }} received",
    example: "Weekly report",
    suggestions: ["{{ $json.title }}", "New lead from {{ $json.source }}", "Weekly report"],
  },
  {
    test: /body|message|content|text$|description/i,
    placeholder: "Hi {{ $json.name }}, your order has shipped.",
    example: "Hello {{ $json.name }} — thanks for signing up.",
    suggestions: [
      "Hello {{ $json.name }}",
      "{{ $json.body }}",
      "Run completed at {{ $now }}",
    ],
    tip: "Supports {{ $json.* }} and helpers like $now, $workflow, $node.",
  },
  {
    test: /path$|file.?path|filename/i,
    placeholder: "/tmp/output.json",
    example: "/data/exports/{{ $now }}.csv",
    suggestions: ["/tmp/output.json", "./data/{{ $json.id }}.json"],
  },
  {
    test: /bucket|container/i,
    placeholder: "my-bucket",
    example: "weftlyflow-prod",
    suggestions: ["{{ $json.bucket }}", "my-bucket", "uploads"],
  },
  {
    test: /region|zone/i,
    placeholder: "us-east-1",
    example: "eu-west-1",
    suggestions: ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"],
  },
  {
    test: /^id$|.*_id$|.*Id$/i,
    placeholder: "abc123",
    example: "{{ $json.id }}",
    suggestions: ["{{ $json.id }}", "{{ $item(0).$node['Trigger'].json.id }}"],
    tip: "Usually the primary key of the row/record you're targeting.",
  },
  {
    test: /cron|schedule|interval/i,
    placeholder: "0 */5 * * * *",
    example: "every 5 minutes",
    suggestions: ["0 * * * * *", "0 */5 * * * *", "0 0 9 * * 1-5"],
    tip: "Standard cron (sec min hour dom mon dow). '0 */5 * * * *' runs every 5 min.",
  },
  {
    test: /table|collection|database/i,
    placeholder: "users",
    example: "orders",
    suggestions: ["users", "orders", "events"],
  },
  {
    test: /column|field$/i,
    placeholder: "created_at",
    example: "updated_at",
    suggestions: ["id", "created_at", "updated_at", "status"],
  },
  {
    test: /port$/i,
    placeholder: "5432",
    example: "5432",
    suggestions: ["80", "443", "5432", "3306", "6379"],
  },
  {
    test: /host$|hostname|server/i,
    placeholder: "db.internal",
    example: "api.example.com",
    suggestions: ["localhost", "db.internal", "api.example.com"],
  },
  {
    test: /limit|page.?size|per.?page/i,
    placeholder: "100",
    example: "100",
    suggestions: ["10", "50", "100", "1000"],
  },
  {
    test: /timeout/i,
    placeholder: "30",
    example: "30 seconds",
    suggestions: ["10", "30", "60", "300"],
    tip: "Seconds to wait before giving up.",
  },
  {
    test: /tags?$/i,
    placeholder: "high-priority,billing",
    example: "staging,urgent",
    suggestions: ["production", "staging", "urgent"],
  },
];

const JSON_EXAMPLE_RULES: Rule[] = [
  {
    test: /headers?$/i,
    example: '{ "Content-Type": "application/json", "X-Request-Id": "={{ $json.id }}" }',
    suggestions: [
      '{ "Content-Type": "application/json" }',
      '{ "Authorization": "Bearer ={{ $credentials.token }}" }',
      '{ "Accept": "application/json" }',
    ],
    tip: "Key/value pairs. Values can be expressions.",
  },
  {
    test: /body|payload|data$/i,
    example: '{ "name": "={{ $json.name }}", "ts": "={{ $now }}" }',
    suggestions: [
      '{ "name": "Acme" }',
      '{ "id": "={{ $json.id }}", "status": "done" }',
      "[]",
    ],
    tip: "Any JSON value. Strings starting with `=` are evaluated as expressions.",
  },
  {
    test: /query|params?$/i,
    example: '{ "page": 1, "per_page": 100 }',
    suggestions: [
      '{ "page": 1, "per_page": 100 }',
      '{ "q": "={{ $json.query }}" }',
    ],
  },
];

/**
 * Derive a FieldHelp record for a given node property. Falls back to a
 * neutral help payload if no rule matches, so callers never get null.
 */
export function helpFor(prop: NodeProperty): FieldHelp {
  const placeholder = prop.placeholder ?? "";
  const rules = prop.type === "json" ? [...JSON_EXAMPLE_RULES, ...NAME_RULES] : NAME_RULES;
  for (const rule of rules) {
    if (rule.test.test(prop.name) || rule.test.test(prop.display_name)) {
      return {
        placeholder: placeholder || rule.placeholder || "",
        example: rule.example ?? null,
        suggestions: rule.suggestions ?? [],
        tip: rule.tip ?? prop.description ?? null,
      };
    }
  }
  // Type-specific defaults.
  if (prop.type === "number") {
    return {
      placeholder: placeholder || "0",
      example: "42",
      suggestions: ["1", "10", "100"],
      tip: prop.description ?? "Any whole or decimal number.",
    };
  }
  if (prop.type === "json") {
    return {
      placeholder: placeholder || "{}",
      example: '{ "key": "value" }',
      suggestions: ["{}", "[]", '{ "id": "={{ $json.id }}" }'],
      tip: prop.description ?? "Any valid JSON. Prefix string values with `=` to evaluate as an expression.",
    };
  }
  if (prop.type === "boolean") {
    return {
      placeholder: "",
      example: null,
      suggestions: [],
      tip: prop.description ?? "Toggle on or off.",
    };
  }
  if (prop.type === "options") {
    const first = prop.options?.[0];
    return {
      placeholder: "",
      example: first ? first.label : null,
      suggestions: [],
      tip: prop.description ?? "Pick one of the allowed values.",
    };
  }
  return {
    placeholder: placeholder || prop.display_name,
    example: null,
    suggestions: [],
    tip: prop.description ?? null,
  };
}
