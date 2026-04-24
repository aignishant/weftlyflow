// Reactive tour controller — drives the global TourOverlay. Tours are
// declared as ordered lists of steps that each reference an on-screen
// element by data-testid (or arbitrary selector). State lives in a module
// singleton so any view can `startTour("home")` or `resetTour("all")` and
// the overlay renders without prop-drilling. Completion is persisted in
// localStorage so a tour only auto-plays on first visit.

import { computed, reactive } from "vue";

export type TourPlacement = "top" | "bottom" | "left" | "right" | "auto";

export interface TourStep {
  /** CSS selector for the element to spotlight. If null, step is centered. */
  target: string | null;
  title: string;
  body: string;
  /** Where the popover should sit relative to the target. */
  placement?: TourPlacement;
  /** Extra vertical offset in px — useful for sticky headers. */
  offset?: number;
}

export interface TourDefinition {
  id: string;
  steps: TourStep[];
}

interface TourState {
  active: TourDefinition | null;
  stepIndex: number;
}

const STORAGE_PREFIX = "weftlyflow.tour.seen.";
const state = reactive<TourState>({
  active: null,
  stepIndex: 0,
});

export const tourState = state;

export const currentStep = computed<TourStep | null>(() => {
  if (!state.active) return null;
  return state.active.steps[state.stepIndex] ?? null;
});

export const totalSteps = computed<number>(() => state.active?.steps.length ?? 0);
export const stepNumber = computed<number>(() => state.stepIndex + 1);
export const isLastStep = computed<boolean>(
  () => !!state.active && state.stepIndex === state.active.steps.length - 1,
);
export const isFirstStep = computed<boolean>(() => state.stepIndex === 0);

function storageKey(id: string): string {
  return `${STORAGE_PREFIX}${id}`;
}

export function hasSeenTour(id: string): boolean {
  try {
    return window.localStorage.getItem(storageKey(id)) === "1";
  } catch {
    return true;
  }
}

function markSeen(id: string): void {
  try {
    window.localStorage.setItem(storageKey(id), "1");
  } catch {
    /* ignore */
  }
}

export function resetTour(id: string | "all"): void {
  try {
    if (id === "all") {
      const keys: string[] = [];
      for (let i = 0; i < window.localStorage.length; i += 1) {
        const k = window.localStorage.key(i);
        if (k && k.startsWith(STORAGE_PREFIX)) keys.push(k);
      }
      keys.forEach((k) => window.localStorage.removeItem(k));
    } else {
      window.localStorage.removeItem(storageKey(id));
    }
  } catch {
    /* ignore */
  }
}

export function startTour(def: TourDefinition, opts: { force?: boolean } = {}): boolean {
  if (!opts.force && hasSeenTour(def.id)) return false;
  state.active = def;
  state.stepIndex = 0;
  return true;
}

export function nextStep(): void {
  if (!state.active) return;
  if (state.stepIndex >= state.active.steps.length - 1) {
    finishTour();
    return;
  }
  state.stepIndex += 1;
}

export function previousStep(): void {
  if (!state.active) return;
  if (state.stepIndex > 0) state.stepIndex -= 1;
}

export function skipTour(): void {
  if (!state.active) return;
  markSeen(state.active.id);
  state.active = null;
  state.stepIndex = 0;
}

export function finishTour(): void {
  if (!state.active) return;
  markSeen(state.active.id);
  state.active = null;
  state.stepIndex = 0;
}

// --- Tour definitions ------------------------------------------------------

export const HOME_TOUR: TourDefinition = {
  id: "home.v2",
  steps: [
    {
      target: null,
      title: "Welcome to Weftlyflow",
      body:
        "Your self-hosted automation workspace. Let's take a 30-second tour of the dashboard so you know where everything lives.",
      placement: "auto",
    },
    {
      target: '[data-testid="hero-card"]',
      title: "Your workspace at a glance",
      body:
        "The hero card greets you, shows system health, and gives you a one-line workflow launcher. Name it, hit Create, and you're in the editor.",
      placement: "bottom",
    },
    {
      target: '[data-testid="quick-actions"]',
      title: "Quick actions",
      body:
        "One-click shortcuts for the things you'll do most: start a new workflow, add a credential, review runs, browse integrations.",
      placement: "bottom",
    },
    {
      target: '[data-testid="stats-row"]',
      title: "Live KPIs",
      body:
        "Total workflows, how many are currently active, how many runs in the last 24h, and your success rate. Updates after every execution.",
      placement: "bottom",
    },
    {
      target: '[data-testid="templates-panel"]',
      title: "Pre-built templates",
      body:
        "Don't start from scratch. Pick a complete automation — uptime guards, Stripe notifiers, RAG chat, ETL pipelines — and land in the editor fully wired.",
      placement: "top",
    },
    {
      target: '[data-testid="integrations-panel"]',
      title: "Integrations gallery",
      body:
        "All 100+ built-in connectors — HTTP, databases, Slack, Stripe, Notion, plus 18 AI providers. Use the search box to jump straight to one.",
      placement: "top",
    },
    {
      target: '[data-testid="workflow-create"]',
      title: "Create your first workflow",
      body:
        "Give it a name above and click Create. You'll land in the editor where we'll pick things up with a second mini-tour.",
      placement: "left",
    },
  ],
};

export const EDITOR_TOUR: TourDefinition = {
  id: "editor.v2",
  steps: [
    {
      target: null,
      title: "The workflow editor",
      body:
        "This is where you build. Three panels: node palette on the left, canvas in the middle, parameter inspector on the right. Let's walk through each.",
      placement: "auto",
    },
    {
      target: '[data-testid="node-palette"]',
      title: "Node palette",
      body:
        "Search or scroll for any of the 100+ nodes. Click one and it lands on the canvas. Tip: press ⌘K (or Ctrl+K) to focus search from anywhere.",
      placement: "right",
    },
    {
      target: ".canvas-area",
      title: "Canvas",
      body:
        "Drag nodes around, wire outputs to inputs by dragging from one handle to another. Click a node to select it; the inspector on the right will show its fields.",
      placement: "top",
    },
    {
      target: ".inspector",
      title: "Parameter inspector",
      body:
        "Every node's parameters render here. Required fields show a red dot; a live counter at the top shows how many are set. Sensitive fields use masked inputs.",
      placement: "left",
    },
    {
      target: ".f-example, .f-chips",
      title: "Examples & suggestions",
      body:
        "Most fields include an 'e.g.' example line and clickable suggestion chips — just click a chip to drop it into the field. Look for the lightbulb and wand icons.",
      placement: "left",
    },
    {
      target: ".f-help-btn",
      title: "Inline tips",
      body:
        "Click the ? next to any field label to expand a tip card with syntax hints, expression helpers like {{ $json.field }}, and common pitfalls.",
      placement: "left",
    },
    {
      target: '[data-testid="editor-save"]',
      title: "Save & run",
      body:
        "⌘S saves, ⌘Enter runs. The Active toggle turns triggers on so scheduled/webhook workflows fire automatically. You're ready — happy automating!",
      placement: "bottom",
    },
  ],
};

export const CREDENTIALS_TOUR: TourDefinition = {
  id: "credentials.v1",
  steps: [
    {
      target: null,
      title: "Credentials vault",
      body:
        "Centralised, encrypted storage for every API key, OAuth token, and DB connection string your workflows need. Secrets are Fernet-encrypted at rest and never surface in logs or UI.",
      placement: "auto",
    },
    {
      target: '[data-testid="new-credential"]',
      title: "Add a new credential",
      body:
        "Pick a type (bearer token, basic auth, OAuth, DB, cloud provider…) and fill the form. Each type has its own schema with masked inputs for secret fields.",
      placement: "left",
    },
    {
      target: '[data-testid="credentials-table"]',
      title: "Your credentials",
      body:
        "All saved credentials appear here. Use the Test button to verify a credential works before wiring it into a workflow — no more debugging auth in production.",
      placement: "top",
    },
  ],
};

export const EXECUTIONS_TOUR: TourDefinition = {
  id: "executions.v1",
  steps: [
    {
      target: null,
      title: "Execution history",
      body:
        "Every workflow run — manual, scheduled, or webhook-triggered — is recorded here with full input/output per node. Think of it as your automation audit log.",
      placement: "auto",
    },
    {
      target: '[data-testid="executions-table"]',
      title: "Runs at a glance",
      body:
        "Status, mode, timing, and the workflow that ran. Click any ID to drill into per-node inputs, outputs, and errors — great for debugging failed runs.",
      placement: "top",
    },
  ],
};
