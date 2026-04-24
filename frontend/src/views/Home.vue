<script setup lang="ts">
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  BarChart3,
  BookOpen,
  Bot,
  Boxes,
  Brain,
  CalendarDays,
  CheckCircle2,
  Circle,
  ClipboardList,
  Clock,
  Database,
  DollarSign,
  Download,
  FileText,
  Github,
  GitBranch,
  Globe,
  Hash,
  KeyRound,
  Layers,
  LifeBuoy,
  Mail,
  MessageSquare,
  Package,
  Play,
  Plus,
  Radio,
  Receipt,
  Rocket,
  Search,
  ShoppingBag,
  Siren,
  Sparkles,
  Sunrise,
  Target,
  Trash2,
  TrendingUp,
  Wand2,
  Zap,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";

import { extractErrorMessage } from "@/api/client";
import { WORKFLOW_TEMPLATES, type WorkflowTemplate } from "@/lib/templates";
import { toast } from "@/lib/toast";
import { HOME_TOUR, startTour } from "@/lib/tour";
import { useAuthStore } from "@/stores/auth";
import { useCredentialsStore } from "@/stores/credentials";
import { useExecutionsStore } from "@/stores/executions";
import { useNodeTypesStore } from "@/stores/nodeTypes";
import { useWorkflowsStore } from "@/stores/workflows";

const store = useWorkflowsStore();
const nodeTypes = useNodeTypesStore();
const executions = useExecutionsStore();
const credentials = useCredentialsStore();
const auth = useAuthStore();
const router = useRouter();

const creating = ref(false);
const newName = ref("");
const createError = ref<string | null>(null);
const search = ref("");
const integrationSearch = ref("");
const systemStatus = ref<"ok" | "degraded" | "down" | "unknown">("unknown");
let healthTimer: ReturnType<typeof setInterval> | null = null;

async function pingHealth(): Promise<void> {
  try {
    const [health, ready] = await Promise.all([
      fetch("/healthz").then((r) => r.ok),
      fetch("/readyz").then((r) => r.ok).catch(() => true),
    ]);
    systemStatus.value = health && ready ? "ok" : health ? "degraded" : "down";
  } catch {
    systemStatus.value = "down";
  }
}

onMounted(async () => {
  await Promise.allSettled([
    store.fetchAll(),
    nodeTypes.loadOnce(),
    executions.fetchList(),
    credentials.fetchAll(),
    pingHealth(),
  ]);
  healthTimer = setInterval(pingHealth, 15_000);
  // Kick the onboarding tour on first visit. Waits a tick so DOM selectors
  // in tour steps resolve after the initial render.
  setTimeout(() => startTour(HOME_TOUR), 400);
});

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer);
});

async function createWorkflow(): Promise<void> {
  const name = newName.value.trim();
  if (!name || creating.value) {
    return;
  }
  creating.value = true;
  createError.value = null;
  try {
    const created = await store.create({
      name,
      nodes: [
        {
          id: "node_trigger",
          name: "Manual Trigger",
          type: "weftlyflow.manual_trigger",
          parameters: {},
          position: [120, 160],
        },
      ],
      connections: [],
    });
    newName.value = "";
    await router.push({ name: "editor", params: { id: created.id } });
  } catch (err) {
    createError.value = extractErrorMessage(err);
  } finally {
    creating.value = false;
  }
}

async function onDelete(id: string, name: string): Promise<void> {
  if (!window.confirm(`Delete workflow "${name}"?`)) {
    return;
  }
  await store.remove(id);
}

// ----- Template gallery -----------------------------------------------------

const installingTemplate = ref<string | null>(null);
const templates = WORKFLOW_TEMPLATES;

const templateIcons: Record<string, unknown> = {
  Siren,
  ShoppingBag,
  Brain,
  GitBranch,
  Database,
  Bot,
  Sunrise,
  ClipboardList,
  BarChart3,
  Mail,
  FileText,
  LifeBuoy,
  Github,
  CalendarDays,
  Rocket,
  TrendingUp,
  MessageSquare,
  AlertTriangle,
  Receipt,
  Globe,
  DollarSign,
  AlertOctagon,
  Target,
  Hash,
};

function iconForTemplate(name: string): unknown {
  return templateIcons[name] ?? Sparkles;
}

async function installTemplate(tpl: WorkflowTemplate): Promise<void> {
  if (installingTemplate.value) return;
  installingTemplate.value = tpl.id;
  try {
    const payload = tpl.build();
    const created = await store.create(payload);
    toast.success(`Installed: ${tpl.name}`, "Opening editor…");
    await router.push({ name: "editor", params: { id: created.id } });
  } catch (err) {
    toast.error("Could not install template", extractErrorMessage(err));
  } finally {
    installingTemplate.value = null;
  }
}

// ----- derived data for the dashboard ---------------------------------------

const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
});

const userLabel = computed(() => {
  const email = auth.email ?? "";
  return email.split("@")[0] || "there";
});

const activeCount = computed(() =>
  store.items.filter((w) => w.active).length,
);

const totalNodes = computed(() =>
  store.items.reduce((acc, w) => acc + w.nodes.length, 0),
);

const recentExecutions = computed(() => {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  return executions.items.filter(
    (e) => new Date(e.started_at).getTime() >= cutoff,
  );
});

const successRate = computed(() => {
  const finished = executions.items.filter((e) => e.finished_at !== null);
  if (finished.length === 0) return null;
  const ok = finished.filter((e) => e.status === "success").length;
  return Math.round((ok / finished.length) * 100);
});

interface Bucket {
  label: string;
  success: number;
  failure: number;
}

const buckets = computed<Bucket[]>(() => {
  const now = new Date();
  const result: Bucket[] = [];
  for (let i = 13; i >= 0; i--) {
    const day = new Date(now);
    day.setDate(day.getDate() - i);
    day.setHours(0, 0, 0, 0);
    const next = new Date(day);
    next.setDate(next.getDate() + 1);
    const inRange = executions.items.filter((e) => {
      const t = new Date(e.started_at).getTime();
      return t >= day.getTime() && t < next.getTime();
    });
    result.push({
      label: day.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      success: inRange.filter((e) => e.status === "success").length,
      failure: inRange.filter((e) => e.status === "error" || e.status === "failed").length,
    });
  }
  return result;
});

const maxBucket = computed(() =>
  Math.max(1, ...buckets.value.map((b) => b.success + b.failure)),
);

const filteredWorkflows = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return store.items;
  return store.items.filter((w) => w.name.toLowerCase().includes(q));
});

const executionsByWorkflow = computed(() => {
  const map = new Map<string, number>();
  for (const e of executions.items) {
    map.set(e.workflow_id, (map.get(e.workflow_id) ?? 0) + 1);
  }
  return map;
});

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function workflowName(id: string): string {
  return store.items.find((w) => w.id === id)?.name ?? id.slice(0, 10);
}

function statusTone(status: string): string {
  if (status === "success") return "ok";
  if (status === "error" || status === "failed") return "bad";
  if (status === "running") return "run";
  return "wait";
}

// ----- credentials / nodes visualizations -----------------------------------

const recentCredentials = computed(() =>
  [...credentials.items]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 6),
);

function credentialTypeLabel(slug: string): string {
  const entry = credentials.types.find((t) => t.slug === slug);
  return entry?.display_name ?? slug;
}

// Deterministic palette picker so a credential type always gets the same hue.
const TYPE_PALETTE = [
  ["#5c8dff", "#8b5cff"],
  ["#3dd28d", "#5c8dff"],
  ["#f0b455", "#f76c6c"],
  ["#8b5cff", "#f76c6c"],
  ["#3dd28d", "#f0b455"],
  ["#5c8dff", "#3dd28d"],
] as const;
function paletteFor(slug: string): readonly [string, string] {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return TYPE_PALETTE[h % TYPE_PALETTE.length];
}
function credentialInitial(slug: string): string {
  const entry = credentials.types.find((t) => t.slug === slug);
  const name = entry?.display_name ?? slug.replace(/^.*\./, "");
  return name.slice(0, 1).toUpperCase();
}

interface CategoryBucket {
  key: string;
  label: string;
  count: number;
  nodes: string[];
}

const nodeCategories = computed<CategoryBucket[]>(() => {
  const map = new Map<string, CategoryBucket>();
  for (const n of nodeTypes.items) {
    const key = (n.category || "other").toLowerCase();
    const bucket = map.get(key) ?? {
      key,
      label: key.charAt(0).toUpperCase() + key.slice(1),
      count: 0,
      nodes: [],
    };
    bucket.count += 1;
    if (bucket.nodes.length < 4) bucket.nodes.push(n.display_name);
    map.set(key, bucket);
  }
  return [...map.values()].sort((a, b) => b.count - a.count);
});

const topNodes = computed(() => nodeTypes.items.slice(0, 8));

// Status donut — arcs for success/error/running/waiting.
interface StatusSlice {
  label: string;
  tone: string;
  count: number;
  color: string;
}

const statusSlices = computed<StatusSlice[]>(() => {
  const buckets: Record<string, number> = {
    success: 0,
    error: 0,
    running: 0,
    waiting: 0,
  };
  for (const e of executions.items) {
    if (e.status === "success") buckets.success += 1;
    else if (e.status === "error" || e.status === "failed") buckets.error += 1;
    else if (e.status === "running") buckets.running += 1;
    else buckets.waiting += 1;
  }
  return [
    { label: "Success", tone: "ok",   count: buckets.success, color: "#3dd28d" },
    { label: "Error",   tone: "bad",  count: buckets.error,   color: "#f76c6c" },
    { label: "Running", tone: "run",  count: buckets.running, color: "#5c8dff" },
    { label: "Waiting", tone: "wait", count: buckets.waiting, color: "#6c7383" },
  ];
});

const statusTotal = computed(() =>
  statusSlices.value.reduce((a, b) => a + b.count, 0),
);

interface DonutArc {
  color: string;
  dash: string;
  offset: number;
}

const donutArcs = computed<DonutArc[]>(() => {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const total = Math.max(1, statusTotal.value);
  let accumulated = 0;
  return statusSlices.value
    .filter((s) => s.count > 0)
    .map((s) => {
      const len = (s.count / total) * circumference;
      const arc: DonutArc = {
        color: s.color,
        dash: `${len} ${circumference - len}`,
        offset: -accumulated,
      };
      accumulated += len;
      return arc;
    });
});

const donutCircumference = 2 * Math.PI * 54;

// ----- integrations -------------------------------------------------------

const integrationNodes = computed(() =>
  nodeTypes.items.filter((n) => n.category === "integration"),
);

const aiNodes = computed(() =>
  nodeTypes.items.filter((n) => n.category === "ai"),
);

const triggerNodes = computed(() =>
  nodeTypes.items.filter((n) => n.category === "trigger"),
);

const filteredIntegrations = computed(() => {
  const q = integrationSearch.value.trim().toLowerCase();
  const base = [...integrationNodes.value, ...aiNodes.value];
  if (!q) return base;
  return base.filter(
    (n) =>
      n.display_name.toLowerCase().includes(q) ||
      n.type.toLowerCase().includes(q),
  );
});

function nodePalette(slug: string): readonly [string, string] {
  return paletteFor(slug);
}
function nodeInitial(n: { display_name: string }): string {
  const parts = n.display_name.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return n.display_name.slice(0, 2).toUpperCase();
}

const systemBadge = computed(() => {
  switch (systemStatus.value) {
    case "ok":       return { label: "All systems operational", tone: "ok",   color: "#3dd28d" };
    case "degraded": return { label: "Degraded performance",    tone: "warn", color: "#f0b455" };
    case "down":     return { label: "API unreachable",         tone: "bad",  color: "#f76c6c" };
    default:         return { label: "Checking…",                tone: "wait", color: "#9aa3b2" };
  }
});

interface QuickAction {
  label: string;
  hint: string;
  icon: typeof Plus;
  to: { name: string };
  tone: "blue" | "green" | "purple" | "amber";
}
const quickActions = computed<QuickAction[]>(() => [
  { label: "New workflow",   hint: "Start a blank canvas",           icon: Plus,       to: { name: "home" },        tone: "blue"   },
  { label: "Add credential", hint: "OAuth / API keys",               icon: KeyRound,   to: { name: "credentials" }, tone: "green"  },
  { label: "Recent runs",    hint: "Inspect latest executions",      icon: Play,       to: { name: "executions" },  tone: "purple" },
  { label: "Browse nodes",   hint: "Discover integrations",          icon: BookOpen,   to: { name: "home" },        tone: "amber"  },
]);
</script>

<template>
  <div class="home">
    <!-- HERO ---------------------------------------------------------- -->
    <section class="hero" data-testid="hero-card">
      <div class="hero-copy">
        <div class="hero-top">
          <p class="eyebrow">
            <Sparkles :size="14" />
            <span>{{ greeting }}, {{ userLabel }}</span>
          </p>
          <span class="sys-badge" :data-tone="systemBadge.tone">
            <span class="sys-dot" :style="{ background: systemBadge.color }" />
            {{ systemBadge.label }}
          </span>
        </div>
        <h1>Your automation workspace</h1>
        <p class="lede">
          Build, run, and observe workflows across APIs, databases, and AI.
          Here is what is happening today.
        </p>
      </div>
      <div class="hero-cta">
        <form class="create-form" @submit.prevent="createWorkflow">
          <input
            v-model="newName"
            data-testid="workflow-name"
            placeholder="Name your next workflow…"
            required
          >
          <button
            type="submit"
            class="primary"
            data-testid="workflow-create"
            :disabled="creating || !newName.trim()"
          >
            <Plus :size="16" />
            <span>{{ creating ? "Creating…" : "Create workflow" }}</span>
          </button>
        </form>
        <p v-if="createError" class="error">{{ createError }}</p>
      </div>
    </section>

    <!-- QUICK ACTIONS ------------------------------------------------- -->
    <section class="quick-actions" data-testid="quick-actions">
      <RouterLink
        v-for="action in quickActions"
        :key="action.label"
        :to="action.to"
        class="qa"
        :data-tone="action.tone"
      >
        <span class="qa-icon">
          <component :is="action.icon" :size="18" />
        </span>
        <span class="qa-body">
          <span class="qa-label">{{ action.label }}</span>
          <span class="qa-hint">{{ action.hint }}</span>
        </span>
      </RouterLink>
    </section>

    <!-- STAT CARDS ---------------------------------------------------- -->
    <section class="stats" data-testid="stats-row">
      <article class="stat" data-tone="blue">
        <div class="stat-icon"><Layers :size="18" /></div>
        <div class="stat-body">
          <p class="stat-label">Workflows</p>
          <p class="stat-value">{{ store.items.length }}</p>
          <p class="stat-sub">{{ totalNodes }} nodes total</p>
        </div>
      </article>
      <article class="stat" data-tone="green">
        <div class="stat-icon"><Zap :size="18" /></div>
        <div class="stat-body">
          <p class="stat-label">Active</p>
          <p class="stat-value">{{ activeCount }}</p>
          <p class="stat-sub">running on triggers</p>
        </div>
      </article>
      <article class="stat" data-tone="purple">
        <div class="stat-icon"><Activity :size="18" /></div>
        <div class="stat-body">
          <p class="stat-label">Runs (24h)</p>
          <p class="stat-value">{{ recentExecutions.length }}</p>
          <p class="stat-sub">{{ executions.items.length }} all-time</p>
        </div>
      </article>
      <article class="stat" data-tone="amber">
        <div class="stat-icon"><TrendingUp :size="18" /></div>
        <div class="stat-body">
          <p class="stat-label">Success rate</p>
          <p class="stat-value">
            {{ successRate === null ? "—" : `${successRate}%` }}
          </p>
          <p class="stat-sub">across finished runs</p>
        </div>
      </article>
    </section>

    <!-- TEMPLATES GALLERY --------------------------------------------- -->
    <section
      class="wf-card templates"
      data-testid="templates-panel"
    >
      <header class="panel-header">
        <div>
          <h2>
            <Rocket :size="16" />
            Pre-built templates
            <span class="count-pill">{{ templates.length }}</span>
          </h2>
          <p class="panel-sub">
            Ship a complete automation in one click — each template lands in the editor fully wired.
          </p>
        </div>
      </header>

      <div class="tpl-grid">
        <article
          v-for="tpl in templates"
          :key="tpl.id"
          class="tpl"
          :data-tone="tpl.tone"
          :data-testid="`template-${tpl.id}`"
        >
          <div class="tpl-head">
            <span class="tpl-icon">
              <component :is="iconForTemplate(tpl.icon)" :size="18" />
            </span>
            <span class="tpl-cat">{{ tpl.category }}</span>
          </div>
          <h3 class="tpl-name">{{ tpl.name }}</h3>
          <p class="tpl-desc">{{ tpl.description }}</p>
          <div class="tpl-stack">
            <span
              v-for="tag in tpl.stack"
              :key="tag"
              class="tpl-tag"
            >{{ tag }}</span>
          </div>
          <button
            class="tpl-cta"
            :data-testid="`template-install-${tpl.id}`"
            :disabled="installingTemplate !== null"
            @click="installTemplate(tpl)"
          >
            <Wand2 :size="14" />
            <span>{{ installingTemplate === tpl.id ? "Installing…" : "Use template" }}</span>
          </button>
        </article>
      </div>
    </section>

    <!-- INTEGRATIONS GALLERY ------------------------------------------ -->
    <section class="wf-card integrations" data-testid="integrations-panel">
      <header class="panel-header">
        <div>
          <h2>
            Integrations
            <span class="count-pill">{{ integrationNodes.length + aiNodes.length }}</span>
          </h2>
          <p class="muted">
            Connect to {{ integrationNodes.length }} services and {{ aiNodes.length }} AI providers
          </p>
        </div>
        <div class="search">
          <Search :size="14" />
          <input
            v-model="integrationSearch"
            placeholder="Search integrations…"
          >
        </div>
      </header>

      <div class="triggers-strip">
        <span class="triggers-label">
          <Radio :size="12" />
          Triggers
        </span>
        <span
          v-for="t in triggerNodes"
          :key="t.type"
          class="trigger-chip"
          :title="t.description"
        >
          {{ t.display_name }}
        </span>
      </div>

      <div v-if="filteredIntegrations.length > 0" class="int-grid">
        <article
          v-for="n in filteredIntegrations"
          :key="n.type"
          class="int-tile"
          :title="n.description"
        >
          <span
            class="int-logo"
            :style="{
              background: `linear-gradient(135deg, ${nodePalette(n.type)[0]}, ${nodePalette(n.type)[1]})`,
              boxShadow: `0 10px 20px -12px ${nodePalette(n.type)[0]}`,
            }"
          >
            <Brain v-if="n.category === 'ai'" :size="14" />
            <span v-else>{{ nodeInitial(n) }}</span>
          </span>
          <span class="int-meta">
            <span class="int-name">{{ n.display_name }}</span>
            <span class="int-cat">
              {{ n.category === "ai" ? "AI" : "Integration" }}
            </span>
          </span>
        </article>
      </div>
      <p v-else class="muted empty">
        No integrations match "{{ integrationSearch }}".
      </p>
    </section>

    <!-- CHART + RECENT RUNS ------------------------------------------- -->
    <section class="panels">
      <article class="wf-card chart-card">
        <header class="panel-header">
          <div>
            <h2>Activity</h2>
            <p class="muted">Executions by day · last 14 days</p>
          </div>
          <span class="legend">
            <span class="dot dot-ok" /> success
            <span class="dot dot-bad" /> error
          </span>
        </header>
        <div class="chart">
          <div
            v-for="(b, i) in buckets"
            :key="i"
            class="bar-col"
            :title="`${b.label} · ${b.success} ok · ${b.failure} err`"
          >
            <div class="bar-stack">
              <div
                class="bar bar-bad"
                :style="{ height: `${(b.failure / maxBucket) * 100}%` }"
              />
              <div
                class="bar bar-ok"
                :style="{ height: `${(b.success / maxBucket) * 100}%` }"
              />
            </div>
            <span v-if="i % 2 === 0" class="bar-label">{{ b.label }}</span>
          </div>
        </div>
      </article>

      <article class="wf-card recent-card">
        <header class="panel-header">
          <div>
            <h2>Recent runs</h2>
            <p class="muted">Latest 8 executions</p>
          </div>
          <RouterLink :to="{ name: 'executions' }" class="link">View all →</RouterLink>
        </header>
        <ul v-if="executions.items.length > 0" class="run-list">
          <li v-for="e in executions.items.slice(0, 8)" :key="e.id">
            <RouterLink
              :to="{ name: 'execution-detail', params: { id: e.id } }"
              class="run-row"
            >
              <span class="run-status" :data-tone="statusTone(e.status)">
                <CheckCircle2 v-if="e.status === 'success'" :size="14" />
                <Clock v-else-if="e.status === 'running'" :size="14" />
                <Circle v-else :size="14" />
              </span>
              <span class="run-name">{{ workflowName(e.workflow_id) }}</span>
              <span class="run-mode">{{ e.mode }}</span>
              <span class="run-time">{{ timeAgo(e.started_at) }}</span>
            </RouterLink>
          </li>
        </ul>
        <p v-else class="muted empty">No runs yet. Create a workflow and hit execute.</p>
      </article>
    </section>

    <!-- STATUS + CREDS + NODES --------------------------------------- -->
    <section class="trio">
      <!-- Status donut -->
      <article class="wf-card donut-card">
        <header class="panel-header">
          <div>
            <h2>Status mix</h2>
            <p class="muted">Distribution of execution outcomes</p>
          </div>
        </header>
        <div class="donut-wrap">
          <svg
            class="donut"
            viewBox="0 0 140 140"
            role="img"
            aria-label="Execution status distribution"
          >
            <circle
              class="donut-track"
              cx="70" cy="70" r="54"
              fill="none"
              stroke="rgba(255,255,255,0.05)"
              stroke-width="16"
            />
            <circle
              v-for="(arc, i) in donutArcs"
              :key="i"
              cx="70" cy="70" r="54"
              fill="none"
              :stroke="arc.color"
              stroke-width="16"
              stroke-linecap="butt"
              :stroke-dasharray="arc.dash"
              :stroke-dashoffset="arc.offset"
              :style="{ filter: `drop-shadow(0 0 6px ${arc.color}66)` }"
              transform="rotate(-90 70 70)"
            />
            <text
              x="70" y="66"
              text-anchor="middle"
              class="donut-total"
            >{{ statusTotal }}</text>
            <text
              x="70" y="84"
              text-anchor="middle"
              class="donut-sub"
            >runs</text>
          </svg>
          <ul class="donut-legend">
            <li v-for="s in statusSlices" :key="s.label">
              <span class="sw" :style="{ background: s.color }" />
              <span class="sw-label">{{ s.label }}</span>
              <span class="sw-val">{{ s.count }}</span>
            </li>
          </ul>
        </div>
      </article>

      <!-- Credentials -->
      <article class="wf-card creds-card">
        <header class="panel-header">
          <div>
            <h2>Credentials</h2>
            <p class="muted">
              {{ credentials.items.length }} stored · {{ credentials.types.length }} types
            </p>
          </div>
          <RouterLink :to="{ name: 'credentials' }" class="link">Manage →</RouterLink>
        </header>

        <ul v-if="recentCredentials.length > 0" class="cred-list">
          <li v-for="c in recentCredentials" :key="c.id">
            <RouterLink :to="{ name: 'credentials' }" class="cred-row">
              <span
                class="cred-icon"
                :style="{
                  background: `linear-gradient(135deg, ${paletteFor(c.type)[0]}, ${paletteFor(c.type)[1]})`,
                  boxShadow: `0 10px 20px -10px ${paletteFor(c.type)[0]}`,
                }"
              >
                {{ credentialInitial(c.type) }}
              </span>
              <span class="cred-body">
                <span class="cred-name">{{ c.name }}</span>
                <span class="cred-type">
                  {{ credentialTypeLabel(c.type) }} · {{ timeAgo(c.updated_at) }}
                </span>
              </span>
            </RouterLink>
          </li>
        </ul>
        <div v-else class="empty-state">
          <KeyRound :size="22" />
          <p class="muted">No credentials yet.</p>
          <RouterLink :to="{ name: 'credentials' }" class="link">Add your first credential →</RouterLink>
        </div>
      </article>

      <!-- Node catalog -->
      <article class="wf-card nodes-card">
        <header class="panel-header">
          <div>
            <h2>Node palette</h2>
            <p class="muted">
              {{ nodeTypes.items.length }} nodes across {{ nodeCategories.length }} categories
            </p>
          </div>
          <span class="link-muted"><Package :size="14" /></span>
        </header>

        <div class="cats">
          <div
            v-for="cat in nodeCategories"
            :key="cat.key"
            class="cat"
            :data-cat="cat.key"
          >
            <div class="cat-head">
              <span class="cat-name">{{ cat.label }}</span>
              <span class="cat-count">{{ cat.count }}</span>
            </div>
            <div class="cat-bar">
              <span
                class="cat-fill"
                :style="{
                  width: `${Math.min(100, (cat.count / (nodeCategories[0]?.count || 1)) * 100)}%`,
                }"
              />
            </div>
            <p class="cat-samples">
              {{ cat.nodes.slice(0, 3).join(" · ") }}
              <span v-if="cat.count > 3"> · +{{ cat.count - 3 }}</span>
            </p>
          </div>
        </div>

        <footer v-if="topNodes.length > 0" class="node-chips">
          <span
            v-for="n in topNodes"
            :key="n.type"
            class="node-chip"
            :title="n.description"
          >
            {{ n.display_name }}
          </span>
        </footer>
      </article>
    </section>

    <!-- WORKFLOW GRID ------------------------------------------------- -->
    <section class="wf-card workflows">
      <header class="panel-header">
        <div>
          <h2>Workflows</h2>
          <p class="muted">
            {{ filteredWorkflows.length }} of {{ store.items.length }}
          </p>
        </div>
        <div class="search">
          <Search :size="14" />
          <input v-model="search" placeholder="Search workflows…">
        </div>
      </header>

      <p v-if="store.loading" class="muted">Loading…</p>
      <p
        v-else-if="store.items.length === 0"
        class="muted empty"
      >
        No workflows yet. Create one above.
      </p>
      <p
        v-else-if="filteredWorkflows.length === 0"
        class="muted empty"
      >
        No workflows match "{{ search }}".
      </p>

      <!-- Preserve the existing data-testid=workflow-table hook for tests
           by wrapping the grid in a table-ish semantics via a custom attr. -->
      <div v-if="filteredWorkflows.length > 0" class="grid" data-testid="workflow-table">
        <article
          v-for="wf in filteredWorkflows"
          :key="wf.id"
          class="wf-tile"
          :data-workflow-id="wf.id"
        >
          <header class="tile-head">
            <span
              class="tile-status"
              :class="wf.active ? 'on' : 'off'"
              :title="wf.active ? 'Active' : 'Inactive'"
            />
            <RouterLink
              :to="{ name: 'editor', params: { id: wf.id } }"
              class="tile-name"
              :data-testid="`workflow-open-${wf.id}`"
            >
              {{ wf.name }}
            </RouterLink>
            <button
              class="tile-delete"
              :title="`Delete ${wf.name}`"
              @click="onDelete(wf.id, wf.name)"
            >
              <Trash2 :size="14" />
            </button>
          </header>

          <div class="tile-meta">
            <span class="chip">
              <Layers :size="12" />
              {{ wf.nodes.length }} nodes
            </span>
            <span class="chip">
              <Activity :size="12" />
              {{ executionsByWorkflow.get(wf.id) ?? 0 }} runs
            </span>
            <span
              v-for="tag in wf.tags.slice(0, 2)"
              :key="tag"
              class="chip tag"
            >
              {{ tag }}
            </span>
          </div>

          <footer class="tile-foot">
            <span class="wf-badge" :class="wf.active ? 'success' : 'waiting'">
              {{ wf.active ? "active" : "inactive" }}
            </span>
            <RouterLink
              :to="{ name: 'editor', params: { id: wf.id } }"
              class="tile-open"
            >
              Open →
            </RouterLink>
          </footer>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 28px 56px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

/* ---------- hero ---------- */
.hero {
  position: relative;
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 28px;
  padding: 28px 28px;
  border-radius: 16px;
  background:
    radial-gradient(600px 240px at 0% 0%, rgba(92, 141, 255, 0.18), transparent 65%),
    radial-gradient(500px 260px at 100% 100%, rgba(139, 92, 255, 0.18), transparent 60%),
    linear-gradient(180deg, rgba(28, 31, 44, 0.75), rgba(22, 25, 36, 0.75));
  border: 1px solid rgba(92, 141, 255, 0.2);
  box-shadow: 0 24px 60px -30px rgba(92, 141, 255, 0.4);
  overflow: hidden;
}
.hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at 20% 0%, black 30%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse at 20% 0%, black 30%, transparent 75%);
  pointer-events: none;
}
.hero-copy { position: relative; }
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 10px 0;
  padding: 4px 10px;
  font-size: 12px;
  color: #b9c5ff;
  background: rgba(92, 141, 255, 0.12);
  border: 1px solid rgba(92, 141, 255, 0.28);
  border-radius: 999px;
}
.hero h1 {
  margin: 0;
  font-size: 28px;
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: -0.01em;
  background: linear-gradient(100deg, #ffffff, #b9c5ff 60%, #8b5cff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.lede {
  margin: 10px 0 0 0;
  color: var(--wf-text-muted);
  font-size: 13.5px;
  max-width: 520px;
  line-height: 1.55;
}
.hero-cta {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}
.create-form {
  display: flex;
  gap: 8px;
  background: rgba(15, 17, 23, 0.55);
  border: 1px solid var(--wf-border);
  border-radius: 12px;
  padding: 6px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.02);
}
.create-form input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--wf-text);
  padding: 8px 10px;
  font-size: 14px;
}
.create-form input::placeholder { color: var(--wf-text-muted); }
.create-form button.primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 14px;
  border: none;
  border-radius: 9px;
  font-weight: 600;
  color: #0f1117;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  cursor: pointer;
  box-shadow: 0 12px 28px -12px rgba(92, 141, 255, 0.6);
  transition: transform 0.12s ease, filter 0.15s ease;
}
.create-form button.primary:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.06);
}
.create-form button.primary:disabled { opacity: 0.6; cursor: not-allowed; }
.error {
  color: var(--wf-danger);
  font-size: 13px;
  margin: 4px 2px 0 2px;
}

/* ---------- stats ---------- */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.stat {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.7), rgba(22, 25, 36, 0.7));
  border: 1px solid var(--wf-border);
  border-radius: 14px;
  overflow: hidden;
  transition: transform 0.15s ease, border-color 0.15s ease;
}
.stat:hover {
  transform: translateY(-2px);
  border-color: rgba(92, 141, 255, 0.35);
}
.stat::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 14px;
  padding: 1px;
  background: linear-gradient(135deg, var(--tone-from, #5c8dff), transparent 55%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  opacity: 0.55;
  pointer-events: none;
}
.stat[data-tone="blue"]   { --tone-from: #5c8dff; --tone-to: #8b5cff; }
.stat[data-tone="green"]  { --tone-from: #3dd28d; --tone-to: #5c8dff; }
.stat[data-tone="purple"] { --tone-from: #8b5cff; --tone-to: #f76c6c; }
.stat[data-tone="amber"]  { --tone-from: #f0b455; --tone-to: #f76c6c; }

.stat-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 11px;
  background: linear-gradient(135deg, var(--tone-from), var(--tone-to));
  color: #0f1117;
  box-shadow: 0 10px 22px -10px var(--tone-from);
}
.stat-label {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--wf-text-muted);
}
.stat-value {
  margin: 2px 0 0 0;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--wf-text);
}
.stat-sub {
  margin: 2px 0 0 0;
  font-size: 12px;
  color: var(--wf-text-muted);
}

/* ---------- panels (chart + recent) ---------- */
.panels {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 14px;
}
.wf-card {
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.7), rgba(22, 25, 36, 0.7));
  border: 1px solid var(--wf-border);
  border-radius: 14px;
  padding: 18px 20px;
}
.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.panel-header h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.muted {
  margin: 2px 0 0 0;
  color: var(--wf-text-muted);
  font-size: 12.5px;
}
.empty { padding: 16px 0; }

.legend {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: var(--wf-text-muted);
}
.dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}
.dot-ok  { background: linear-gradient(135deg, #3dd28d, #5c8dff); }
.dot-bad { background: linear-gradient(135deg, #f76c6c, #f0b455); }

.chart {
  display: grid;
  grid-template-columns: repeat(14, 1fr);
  gap: 6px;
  align-items: end;
  height: 180px;
  padding: 4px 0 22px 0;
  position: relative;
}
.bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  height: 100%;
  position: relative;
}
.bar-stack {
  display: flex;
  flex-direction: column-reverse;
  justify-content: flex-end;
  width: 100%;
  height: 100%;
  gap: 2px;
}
.bar {
  width: 100%;
  border-radius: 4px 4px 1px 1px;
  transition: filter 0.15s ease, transform 0.15s ease;
  min-height: 0;
}
.bar:hover { filter: brightness(1.15); }
.bar-ok {
  background: linear-gradient(180deg, #5c8dff, #3dd28d);
  box-shadow: 0 0 14px -4px rgba(92, 141, 255, 0.45);
}
.bar-bad {
  background: linear-gradient(180deg, #f76c6c, #f0b455);
}
.bar-label {
  position: absolute;
  bottom: -18px;
  font-size: 10px;
  color: var(--wf-text-muted);
  white-space: nowrap;
}

/* recent runs */
.link {
  font-size: 12px;
  color: #b9c5ff;
  text-decoration: none;
}
.link:hover { color: #ffffff; }
.run-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.run-row {
  display: grid;
  grid-template-columns: 22px 1fr auto auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 9px;
  color: var(--wf-text);
  text-decoration: none;
  transition: background 0.15s ease;
}
.run-row:hover { background: rgba(255, 255, 255, 0.04); }
.run-status { display: grid; place-items: center; }
.run-status[data-tone="ok"]   { color: #3dd28d; }
.run-status[data-tone="bad"]  { color: #f76c6c; }
.run-status[data-tone="run"]  { color: #5c8dff; }
.run-status[data-tone="wait"] { color: var(--wf-text-muted); }
.run-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-mode {
  font-size: 11px;
  color: var(--wf-text-muted);
  padding: 2px 6px;
  border: 1px solid var(--wf-border);
  border-radius: 6px;
}
.run-time {
  font-size: 11.5px;
  color: var(--wf-text-muted);
}

/* ---------- workflow grid ---------- */
.workflows { padding: 18px 20px 22px; }
.search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: rgba(15, 17, 23, 0.55);
  border: 1px solid var(--wf-border);
  border-radius: 9px;
  color: var(--wf-text-muted);
}
.search input {
  background: transparent;
  border: none;
  outline: none;
  color: var(--wf-text);
  font-size: 13px;
  width: 200px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
  margin-top: 6px;
}
.wf-tile {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: linear-gradient(180deg, rgba(22, 25, 36, 0.8), rgba(15, 17, 23, 0.8));
  border: 1px solid var(--wf-border);
  border-radius: 12px;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
.wf-tile:hover {
  transform: translateY(-2px);
  border-color: rgba(92, 141, 255, 0.4);
  box-shadow: 0 20px 40px -24px rgba(92, 141, 255, 0.5);
}
.tile-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.tile-status {
  width: 10px; height: 10px;
  border-radius: 50%;
  flex: 0 0 auto;
}
.tile-status.on {
  background: #3dd28d;
  box-shadow: 0 0 0 3px rgba(61, 210, 141, 0.2);
}
.tile-status.off {
  background: var(--wf-border);
}
.tile-name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--wf-text);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tile-name:hover { color: #b9c5ff; }
.tile-delete {
  background: transparent;
  border: 1px solid transparent;
  color: var(--wf-text-muted);
  padding: 4px;
  border-radius: 7px;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.tile-delete:hover {
  color: var(--wf-danger);
  background: rgba(247, 108, 108, 0.12);
  border-color: rgba(247, 108, 108, 0.3);
}
.tile-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--wf-text-muted);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--wf-border);
}
.chip.tag {
  color: #b9c5ff;
  background: rgba(92, 141, 255, 0.1);
  border-color: rgba(92, 141, 255, 0.25);
}
.tile-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 6px;
  border-top: 1px dashed var(--wf-border);
}
.tile-open {
  font-size: 12px;
  color: #b9c5ff;
  text-decoration: none;
}
.tile-open:hover { color: #ffffff; }

/* ---------- trio: status / creds / nodes ---------- */
.trio {
  display: grid;
  grid-template-columns: 0.9fr 1.3fr 1.5fr;
  gap: 14px;
}

/* donut */
.donut-card { display: flex; flex-direction: column; }
.donut-wrap {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 14px;
  align-items: center;
  padding-top: 4px;
}
.donut { width: 140px; height: 140px; }
.donut-total {
  font-size: 24px;
  font-weight: 700;
  fill: var(--wf-text);
}
.donut-sub {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: var(--wf-text-muted);
}
.donut-legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.donut-legend li {
  display: grid;
  grid-template-columns: 12px 1fr auto;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
}
.sw {
  width: 10px; height: 10px;
  border-radius: 3px;
  display: inline-block;
}
.sw-label { color: var(--wf-text-muted); }
.sw-val { color: var(--wf-text); font-weight: 600; font-variant-numeric: tabular-nums; }

/* credentials list */
.creds-card { display: flex; flex-direction: column; }
.cred-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cred-row {
  display: grid;
  grid-template-columns: 34px 1fr;
  align-items: center;
  gap: 10px;
  padding: 8px 8px;
  border-radius: 10px;
  text-decoration: none;
  color: var(--wf-text);
  transition: background 0.15s ease;
}
.cred-row:hover { background: rgba(255, 255, 255, 0.04); }
.cred-icon {
  display: grid;
  place-items: center;
  width: 34px; height: 34px;
  border-radius: 10px;
  color: #0f1117;
  font-weight: 700;
  font-size: 14px;
}
.cred-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.cred-name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cred-type {
  font-size: 11px;
  color: var(--wf-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 8px;
  color: var(--wf-text-muted);
}

/* node palette */
.nodes-card { display: flex; flex-direction: column; gap: 12px; }
.link-muted { color: var(--wf-text-muted); }
.cats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
}
.cat { display: flex; flex-direction: column; gap: 4px; }
.cat-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.cat-name {
  font-size: 12px;
  color: var(--wf-text);
  text-transform: capitalize;
  font-weight: 500;
}
.cat-count {
  font-size: 11px;
  color: var(--wf-text-muted);
  font-variant-numeric: tabular-nums;
}
.cat-bar {
  height: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  overflow: hidden;
}
.cat-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #5c8dff, #8b5cff);
  transition: width 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.cat[data-cat="trigger"] .cat-fill,
.cat[data-cat="triggers"] .cat-fill   { background: linear-gradient(90deg, #3dd28d, #5c8dff); }
.cat[data-cat="ai"] .cat-fill          { background: linear-gradient(90deg, #8b5cff, #f76c6c); }
.cat[data-cat="transform"] .cat-fill   { background: linear-gradient(90deg, #f0b455, #f76c6c); }
.cat[data-cat="flow"] .cat-fill        { background: linear-gradient(90deg, #5c8dff, #3dd28d); }
.cat[data-cat="helpers"] .cat-fill     { background: linear-gradient(90deg, #6c7383, #9aa3b2); }

.cat-samples {
  margin: 0;
  font-size: 11px;
  color: var(--wf-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.node-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 10px;
  margin-top: 2px;
  border-top: 1px dashed var(--wf-border);
}
.node-chip {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: #b9c5ff;
  background: rgba(92, 141, 255, 0.1);
  border: 1px solid rgba(92, 141, 255, 0.25);
  cursor: default;
}

/* ---------- hero status badge + quick actions ---------- */
.hero-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.sys-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--wf-text-muted);
  background: rgba(15, 17, 23, 0.5);
  border: 1px solid var(--wf-border);
}
.sys-badge[data-tone="ok"]   { color: #c9e9d8; border-color: rgba(61, 210, 141, 0.35); }
.sys-badge[data-tone="warn"] { color: #f5d9a9; border-color: rgba(240, 180, 85, 0.35); }
.sys-badge[data-tone="bad"]  { color: #f8c5c5; border-color: rgba(247, 108, 108, 0.35); }
.sys-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.04);
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: 0.55; transform: scale(0.85); }
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.qa {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  text-decoration: none;
  color: var(--wf-text);
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.75), rgba(22, 25, 36, 0.75));
  border: 1px solid var(--wf-border);
  position: relative;
  overflow: hidden;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
.qa::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--qa-from, #5c8dff), transparent 55%);
  opacity: 0.12;
  pointer-events: none;
}
.qa:hover {
  transform: translateY(-2px);
  border-color: var(--qa-from, rgba(92, 141, 255, 0.5));
  box-shadow: 0 16px 36px -20px var(--qa-from, rgba(92, 141, 255, 0.5));
}
.qa[data-tone="blue"]   { --qa-from: #5c8dff; --qa-to: #8b5cff; }
.qa[data-tone="green"]  { --qa-from: #3dd28d; --qa-to: #5c8dff; }
.qa[data-tone="purple"] { --qa-from: #8b5cff; --qa-to: #f76c6c; }
.qa[data-tone="amber"]  { --qa-from: #f0b455; --qa-to: #f76c6c; }
.qa-icon {
  display: grid;
  place-items: center;
  width: 38px; height: 38px;
  border-radius: 10px;
  color: #0f1117;
  background: linear-gradient(135deg, var(--qa-from), var(--qa-to));
  box-shadow: 0 8px 20px -10px var(--qa-from);
  flex: 0 0 auto;
}
.qa-body { display: flex; flex-direction: column; min-width: 0; }
.qa-label { font-size: 13.5px; font-weight: 600; }
.qa-hint  { font-size: 11px; color: var(--wf-text-muted); }

/* ---------- templates ---------- */
.templates { padding: 18px 20px 20px; }
.tpl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
  margin-top: 10px;
}
.tpl {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 14px 12px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.85), rgba(22, 25, 36, 0.9));
  border: 1px solid var(--wf-border);
  overflow: hidden;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.2s ease;
}
.tpl::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 14px;
  padding: 1px;
  background: linear-gradient(135deg, var(--tpl-a, #5c8dff), transparent 55%, var(--tpl-b, #8b5cff));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
  opacity: 0.5;
  transition: opacity 0.2s ease;
}
.tpl:hover {
  transform: translateY(-2px);
  box-shadow: 0 18px 40px -20px rgba(92, 141, 255, 0.45);
}
.tpl:hover::before { opacity: 1; }
.tpl[data-tone="blue"]   { --tpl-a: #5c8dff; --tpl-b: #8b5cff; }
.tpl[data-tone="green"]  { --tpl-a: #3dd28d; --tpl-b: #5c8dff; }
.tpl[data-tone="purple"] { --tpl-a: #8b5cff; --tpl-b: #f76cc6; }
.tpl[data-tone="amber"]  { --tpl-a: #f0b455; --tpl-b: #f76c6c; }
.tpl[data-tone="pink"]   { --tpl-a: #f76cc6; --tpl-b: #8b5cff; }
.tpl[data-tone="teal"]   { --tpl-a: #3dd28d; --tpl-b: #55c8e6; }

.tpl-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tpl-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  color: #0f1117;
  background: linear-gradient(135deg, var(--tpl-a, #5c8dff), var(--tpl-b, #8b5cff));
  box-shadow: 0 8px 20px -10px rgba(92, 141, 255, 0.6),
              inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}
.tpl-cat {
  margin-left: auto;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #b9c5ff;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(92, 141, 255, 0.12);
  border: 1px solid rgba(92, 141, 255, 0.28);
}
.tpl-name {
  margin: 2px 0 0 0;
  font-size: 14.5px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--wf-text);
}
.tpl-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--wf-text-muted);
  flex: 1;
}
.tpl-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.tpl-tag {
  font-size: 10.5px;
  font-family: var(--wf-font-mono);
  color: var(--wf-text-muted);
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--wf-border);
}
.tpl-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 6px;
  padding: 8px 12px;
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: #0f1117;
  background: linear-gradient(135deg, var(--tpl-a, #5c8dff), var(--tpl-b, #8b5cff));
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.15s ease, filter 0.15s ease;
  box-shadow: 0 10px 24px -12px rgba(92, 141, 255, 0.65),
              inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}
.tpl-cta:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.05);
}
.tpl-cta:disabled {
  opacity: 0.7;
  cursor: progress;
}
.panel-sub {
  margin: 2px 0 0 0;
  font-size: 12px;
  color: var(--wf-text-muted);
}

/* ---------- integrations ---------- */
.integrations { padding: 18px 20px 20px; }
.count-pill {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #b9c5ff;
  background: rgba(92, 141, 255, 0.12);
  border: 1px solid rgba(92, 141, 255, 0.28);
  border-radius: 999px;
  vertical-align: middle;
}
.triggers-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  margin: 0 0 14px 0;
  background: rgba(15, 17, 23, 0.4);
  border: 1px dashed var(--wf-border);
  border-radius: 10px;
}
.triggers-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--wf-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-right: 4px;
}
.trigger-chip {
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  color: #bff2d9;
  background: rgba(61, 210, 141, 0.12);
  border: 1px solid rgba(61, 210, 141, 0.3);
}
.int-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(92, 141, 255, 0.4) transparent;
}
.int-grid::-webkit-scrollbar       { width: 8px; }
.int-grid::-webkit-scrollbar-thumb { background: rgba(92, 141, 255, 0.25); border-radius: 4px; }
.int-tile {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(22, 25, 36, 0.6);
  border: 1px solid var(--wf-border);
  transition: transform 0.12s ease, border-color 0.15s ease, background 0.15s ease;
  cursor: default;
}
.int-tile:hover {
  transform: translateY(-1px);
  border-color: rgba(92, 141, 255, 0.4);
  background: rgba(22, 25, 36, 0.9);
}
.int-logo {
  display: grid;
  place-items: center;
  width: 32px; height: 32px;
  border-radius: 9px;
  color: #0f1117;
  font-weight: 700;
  font-size: 12px;
  flex: 0 0 auto;
}
.int-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
}
.int-name {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--wf-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.int-cat {
  font-size: 10.5px;
  color: var(--wf-text-muted);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* ---------- responsive ---------- */
@media (max-width: 1080px) {
  .trio { grid-template-columns: 1fr 1fr; }
  .nodes-card { grid-column: span 2; }
}
@media (max-width: 960px) {
  .hero { grid-template-columns: 1fr; }
  .stats { grid-template-columns: repeat(2, 1fr); }
  .quick-actions { grid-template-columns: repeat(2, 1fr); }
  .panels { grid-template-columns: 1fr; }
  .trio { grid-template-columns: 1fr; }
  .nodes-card { grid-column: auto; }
  .donut-wrap { grid-template-columns: 140px 1fr; }
  .cats { grid-template-columns: 1fr; }
}
@media (max-width: 520px) {
  .stats { grid-template-columns: 1fr; }
  .chart { grid-template-columns: repeat(7, 1fr); }
  .bar-col:nth-child(2n) { display: none; }
}
</style>
