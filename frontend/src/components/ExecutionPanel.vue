<script setup lang="ts">
// Bottom drawer that shows the last run's status + per-node run data.
//
// Rows resolve node ids → display names via the `nodes` prop. Each row
// expands into a tabbed inspector (Output · Error · Metadata) with item
// paging, copy-to-clipboard, and raw-response download.

import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clipboard,
  ClipboardCheck,
  Clock,
  Download,
  Hash,
  Info,
  Play,
  Zap,
} from "lucide-vue-next";
import { computed, ref, watch } from "vue";

import Badge from "@/components/ui/Badge.vue";
import Button from "@/components/ui/Button.vue";
import { cn } from "@/lib/utils";
import type { ExecutionDetail, NodeType, WorkflowNode } from "@/types/api";

const props = defineProps<{
  execution: ExecutionDetail | null;
  running: boolean;
  errorMessage: string | null;
  nodes?: WorkflowNode[];
  nodeTypes?: NodeType[];
}>();

const emit = defineEmits<{
  (event: "run"): void;
}>();

type NodeSummary = {
  nodeId: string;
  displayName: string;
  typeSlug: string;
  category: string;
  status: "success" | "error" | "disabled" | "unknown";
  items: number;
  ports: number;
  durationMs: number;
  startedAt: string | null;
  samples: Record<string, unknown>[];
  errorMessage: string | null;
};

const expanded = ref<Record<string, boolean>>({});
const activeTab = ref<Record<string, "output" | "error" | "metadata">>({});
const activeItemIdx = ref<Record<string, number>>({});
const copiedKey = ref<string | null>(null);

function nodeMeta(nodeId: string): { name: string; slug: string; category: string } {
  const node = props.nodes?.find((n) => n.id === nodeId);
  const slug = node?.type ?? "";
  const typeInfo = props.nodeTypes?.find((t) => t.type === slug);
  return {
    name: node?.name ?? nodeId,
    slug,
    category: typeInfo?.category ?? "core",
  };
}

const CATEGORY_META: Record<string, { from: string; to: string }> = {
  trigger:     { from: "#3dd28d", to: "#5c8dff" },
  core:        { from: "#5c8dff", to: "#8b5cff" },
  integration: { from: "#f0b455", to: "#f76c6c" },
  ai:          { from: "#8b5cff", to: "#f76cc6" },
  helpers:     { from: "#6c7383", to: "#9aa3b2" },
  transform:   { from: "#55c8e6", to: "#3dd28d" },
  flow:        { from: "#5c8dff", to: "#3dd28d" },
};
function catGradient(cat: string): string {
  const meta = CATEGORY_META[cat] ?? CATEGORY_META.core;
  return `linear-gradient(135deg, ${meta.from}, ${meta.to})`;
}

const nodeSummaries = computed<NodeSummary[]>(() => {
  if (!props.execution) return [];
  return Object.entries(props.execution.run_data).map(([nodeId, runs]) => {
    const last = runs[runs.length - 1];
    const ports = last?.items ?? [];
    const flat = ports.flat();
    const samples = flat.map((i) => i.json ?? {});
    const meta = nodeMeta(nodeId);
    return {
      nodeId,
      displayName: meta.name,
      typeSlug: meta.slug,
      category: meta.category,
      status: (last?.status ?? "unknown") as NodeSummary["status"],
      items: flat.length,
      ports: ports.length,
      durationMs: last?.execution_time_ms ?? 0,
      startedAt: last?.started_at ?? null,
      samples,
      errorMessage: last?.error?.message ?? null,
    };
  });
});

const totalItems = computed(() =>
  nodeSummaries.value.reduce((acc, r) => acc + r.items, 0),
);
const totalDurationMs = computed(() => {
  if (!props.execution?.finished_at) return null;
  const start = new Date(props.execution.started_at).getTime();
  const end = new Date(props.execution.finished_at).getTime();
  return Number.isFinite(end - start) ? end - start : null;
});
const maxItemsForBar = computed(() =>
  Math.max(1, ...nodeSummaries.value.map((r) => r.items)),
);
const failedCount = computed(() =>
  nodeSummaries.value.filter((r) => r.status === "error").length,
);

type BadgeVariant = "success" | "danger" | "muted" | "accent";

function statusBadgeVariant(status: string): BadgeVariant {
  if (status === "success") return "success";
  if (status === "error") return "danger";
  if (status === "running") return "accent";
  return "muted";
}

function toggleExpanded(nodeId: string): void {
  expanded.value = { ...expanded.value, [nodeId]: !expanded.value[nodeId] };
  if (!activeTab.value[nodeId]) {
    activeTab.value = { ...activeTab.value, [nodeId]: "output" };
  }
  if (!activeItemIdx.value[nodeId]) {
    activeItemIdx.value = { ...activeItemIdx.value, [nodeId]: 0 };
  }
}

function setTab(nodeId: string, tab: "output" | "error" | "metadata"): void {
  activeTab.value = { ...activeTab.value, [nodeId]: tab };
}

function setItemIdx(nodeId: string, idx: number): void {
  activeItemIdx.value = { ...activeItemIdx.value, [nodeId]: idx };
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} s`;
  return `${(ms / 60_000).toFixed(1)} m`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const hh = d.getHours().toString().padStart(2, "0");
  const mm = d.getMinutes().toString().padStart(2, "0");
  const ss = d.getSeconds().toString().padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

async function copyJson(key: string, value: unknown): Promise<void> {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    copiedKey.value = key;
    setTimeout(() => {
      if (copiedKey.value === key) copiedKey.value = null;
    }, 1200);
  } catch {
    /* clipboard not available — silently ignore */
  }
}

function downloadExecution(): void {
  if (!props.execution) return;
  const blob = new Blob([JSON.stringify(props.execution, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `execution-${props.execution.id}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// Lightweight JSON syntax highlighter — avoids a dependency while still
// giving keys / strings / numbers / booleans / null their own color.
function highlightJson(value: unknown): string {
  const raw = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const escaped = raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped.replace(
    /("(?:\\.|[^"\\])*"(?:\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let cls = "jn";
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? "jk" : "js";
      } else if (/true|false/.test(match)) {
        cls = "jb";
      } else if (/null/.test(match)) {
        cls = "jnull";
      }
      return `<span class="${cls}">${match}</span>`;
    },
  );
}

// Auto-flip tab to "error" when an errored row is expanded.
watch(expanded, (next) => {
  for (const [nodeId, isOpen] of Object.entries(next)) {
    if (!isOpen) continue;
    const row = nodeSummaries.value.find((r) => r.nodeId === nodeId);
    if (row?.status === "error" && !activeTab.value[nodeId]) {
      activeTab.value = { ...activeTab.value, [nodeId]: "error" };
    }
  }
}, { deep: true });
</script>

<template>
  <section
    class="run-panel"
    data-testid="execution-panel"
  >
    <header class="run-head">
      <div class="run-head-main">
        <h3 class="run-title">
          <Zap :size="14" />
          Last execution
        </h3>

        <Badge
          v-if="execution && !running"
          :variant="statusBadgeVariant(execution.status)"
          dot
        >
          {{ execution.status }}
        </Badge>

        <Badge
          v-if="running"
          variant="accent"
          dot
          pulse
        >
          Running
        </Badge>

        <span
          v-if="execution"
          class="run-chip"
          :title="`Started ${execution.started_at}`"
        >
          <Clock :size="11" />
          {{ formatTime(execution.started_at) }}
        </span>

        <span
          v-if="totalDurationMs !== null && !running"
          class="run-chip"
        >
          <Clock :size="11" />
          {{ formatDuration(totalDurationMs) }}
        </span>

        <span v-if="execution && !running" class="run-chip">
          <Hash :size="11" />
          {{ totalItems }} item{{ totalItems === 1 ? "" : "s" }}
        </span>

        <span v-if="execution && !running" class="run-chip">
          <Info :size="11" />
          {{ nodeSummaries.length }} node{{ nodeSummaries.length === 1 ? "" : "s" }}
        </span>

        <span
          v-if="execution && failedCount > 0 && !running"
          class="run-chip run-chip-bad"
        >
          <AlertCircle :size="11" />
          {{ failedCount }} failed
        </span>

        <span
          v-if="execution && !running"
          class="run-chip run-chip-mono"
          :title="`Mode: ${execution.mode}`"
        >
          {{ execution.mode }}
        </span>
      </div>

      <div class="run-head-actions">
        <button
          v-if="execution && !running"
          class="run-action"
          title="Download JSON"
          @click="downloadExecution"
        >
          <Download :size="13" />
        </button>
        <Button
          variant="primary"
          size="sm"
          data-testid="execute-button"
          :loading="running"
          :disabled="running"
          @click="emit('run')"
        >
          <Play
            v-if="!running"
            class="h-3.5 w-3.5"
          />
          {{ running ? "Running" : "Execute" }}
        </Button>
      </div>
    </header>

    <div
      v-if="errorMessage"
      class="run-error"
    >
      <AlertCircle :size="14" />
      <div class="run-error-body">
        <span class="run-error-title">Execution error</span>
        <span class="run-error-msg">{{ errorMessage }}</span>
      </div>
    </div>

    <div
      v-if="!execution && !running && !errorMessage"
      class="run-empty"
    >
      <Play :size="20" />
      <p class="run-empty-title">No runs yet.</p>
      <p class="run-empty-sub">
        Click Execute to run the workflow with a single empty item.
      </p>
    </div>

    <div
      v-if="execution"
      class="run-grid"
      data-testid="run-data"
    >
      <article
        v-for="row in nodeSummaries"
        :key="row.nodeId"
        :class="cn('run-card', `status-${row.status}`)"
        :data-node-id="row.nodeId"
      >
        <button
          type="button"
          class="run-row"
          @click="toggleExpanded(row.nodeId)"
        >
          <ChevronRight
            :class="cn(
              'run-chev',
              expanded[row.nodeId] && 'open',
            )"
          />

          <span
            class="run-icon"
            :style="{ background: catGradient(row.category) }"
          >
            <CheckCircle2
              v-if="row.status === 'success'"
              :size="13"
            />
            <AlertCircle
              v-else-if="row.status === 'error'"
              :size="13"
            />
            <Clock
              v-else
              :size="13"
            />
          </span>

          <div class="run-meta">
            <span class="run-name" :title="row.displayName">
              {{ row.displayName }}
            </span>
            <span class="run-slug" :title="row.typeSlug || row.nodeId">
              {{ row.typeSlug || row.nodeId }}
            </span>
          </div>

          <div class="run-stats">
            <span class="run-stat" :title="`${row.items} items across ${row.ports} port(s)`">
              <Hash :size="10" />
              {{ row.items }}
            </span>
            <span class="run-stat" :title="`Duration: ${formatDuration(row.durationMs)}`">
              <Clock :size="10" />
              {{ formatDuration(row.durationMs) }}
            </span>
          </div>

          <div class="run-bar">
            <span
              class="run-bar-fill"
              :style="{
                width: `${(row.items / maxItemsForBar) * 100}%`,
                background: catGradient(row.category),
              }"
            />
          </div>
        </button>

        <div
          v-if="expanded[row.nodeId]"
          class="run-body"
        >
          <div class="run-tabs">
            <button
              :class="cn('run-tab', (activeTab[row.nodeId] ?? 'output') === 'output' && 'active')"
              @click="setTab(row.nodeId, 'output')"
            >
              Output
              <span class="run-tab-pill">{{ row.items }}</span>
            </button>
            <button
              v-if="row.errorMessage"
              :class="cn('run-tab', activeTab[row.nodeId] === 'error' && 'active', 'danger')"
              @click="setTab(row.nodeId, 'error')"
            >
              Error
            </button>
            <button
              :class="cn('run-tab', activeTab[row.nodeId] === 'metadata' && 'active')"
              @click="setTab(row.nodeId, 'metadata')"
            >
              Metadata
            </button>
            <div class="run-tab-spacer" />
            <button
              class="run-copy"
              :title="copiedKey === row.nodeId ? 'Copied!' : 'Copy full response'"
              @click="copyJson(row.nodeId, row.samples)"
            >
              <ClipboardCheck v-if="copiedKey === row.nodeId" :size="12" />
              <Clipboard v-else :size="12" />
            </button>
          </div>

          <div
            v-if="(activeTab[row.nodeId] ?? 'output') === 'output'"
            class="run-output"
          >
            <div
              v-if="row.samples.length > 1"
              class="run-items"
            >
              <span class="run-items-label">Items</span>
              <button
                v-for="(_, idx) in row.samples"
                :key="idx"
                :class="cn('run-item', (activeItemIdx[row.nodeId] ?? 0) === idx && 'active')"
                @click="setItemIdx(row.nodeId, idx)"
              >
                #{{ idx + 1 }}
              </button>
            </div>
            <pre
              v-if="row.samples.length > 0"
              class="run-json"
              v-html="highlightJson(row.samples[activeItemIdx[row.nodeId] ?? 0])"
            />
            <p v-else class="run-empty-body">No items returned by this node.</p>
          </div>

          <div
            v-else-if="activeTab[row.nodeId] === 'error' && row.errorMessage"
            class="run-errmsg"
          >
            <AlertCircle :size="14" />
            <pre>{{ row.errorMessage }}</pre>
          </div>

          <div
            v-else-if="activeTab[row.nodeId] === 'metadata'"
            class="run-kv"
          >
            <dl>
              <dt>Node ID</dt><dd class="mono">{{ row.nodeId }}</dd>
              <dt>Type</dt><dd class="mono">{{ row.typeSlug || "—" }}</dd>
              <dt>Category</dt><dd>{{ row.category }}</dd>
              <dt>Status</dt><dd>{{ row.status }}</dd>
              <dt>Items</dt><dd>{{ row.items }} across {{ row.ports }} port(s)</dd>
              <dt>Duration</dt><dd>{{ formatDuration(row.durationMs) }}</dd>
              <dt>Started</dt><dd class="mono">{{ row.startedAt ?? "—" }}</dd>
            </dl>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.run-panel {
  display: flex;
  flex-direction: column;
  max-height: 55%;
  overflow-y: auto;
  border-top: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  background:
    linear-gradient(180deg, rgba(28, 31, 44, 0.6), rgba(18, 20, 28, 0.6)),
    var(--color-surface, #161924);
  padding: 12px 16px 14px;
  gap: 10px;
}

/* ---------- header ---------- */
.run-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.run-head-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}
.run-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.run-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--color-foreground, #ffffff);
}
.run-title :deep(svg) {
  color: #f0b455;
  filter: drop-shadow(0 0 6px rgba(240, 180, 85, 0.4));
}
.run-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--color-foreground-muted, #c4cad4);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  white-space: nowrap;
}
.run-chip-mono {
  font-family: var(--wf-font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  letter-spacing: 0.02em;
  text-transform: lowercase;
}
.run-chip-bad {
  color: #f8c5c5;
  background: rgba(247, 108, 108, 0.12);
  border-color: rgba(247, 108, 108, 0.3);
}
.run-action {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: transparent;
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  color: var(--color-foreground-muted, #c4cad4);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.run-action:hover {
  color: var(--color-foreground, #ffffff);
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(92, 141, 255, 0.35);
}

/* ---------- error banner ---------- */
.run-error {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(247, 108, 108, 0.1);
  border: 1px solid rgba(247, 108, 108, 0.35);
  color: #f8c5c5;
}
.run-error :deep(svg) { margin-top: 2px; flex: 0 0 auto; }
.run-error-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.run-error-title { font-size: 12px; font-weight: 700; }
.run-error-msg { font-size: 12px; line-height: 1.45; color: #f0b0b0; word-break: break-word; }

/* ---------- empty state ---------- */
.run-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 28px 8px;
  text-align: center;
  color: var(--color-foreground-subtle, #8c93a1);
}
.run-empty :deep(svg) { opacity: 0.6; margin-bottom: 4px; }
.run-empty-title { margin: 0; font-size: 13px; color: var(--color-foreground-muted, #c4cad4); }
.run-empty-sub { margin: 2px 0 0; font-size: 11.5px; }
.run-empty-body {
  margin: 0;
  padding: 10px 0;
  color: var(--color-foreground-subtle, #8c93a1);
  font-size: 12px;
  text-align: center;
}

/* ---------- grid of node result cards ---------- */
.run-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 10px;
}
.run-card {
  position: relative;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.85), rgba(18, 20, 28, 0.9));
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  overflow: hidden;
  transition: border-color 0.15s ease, transform 0.15s ease;
}
.run-card:hover { border-color: rgba(92, 141, 255, 0.35); }
.run-card.status-error { border-color: rgba(247, 108, 108, 0.4); }
.run-card.status-success { /* neutral, already fine */ }

.run-row {
  position: relative;
  display: grid;
  grid-template-columns: 12px 30px 1fr auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px 12px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  color: inherit;
}
.run-row:hover { background: rgba(255, 255, 255, 0.02); }
.run-chev {
  width: 12px;
  height: 12px;
  color: var(--color-foreground-subtle, #8c93a1);
  transition: transform 0.15s ease;
  flex: 0 0 auto;
}
.run-chev.open { transform: rotate(90deg); }
.run-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  color: #0f1117;
  box-shadow: 0 6px 14px -8px rgba(92, 141, 255, 0.45),
              inset 0 0 0 1px rgba(255, 255, 255, 0.18);
  flex: 0 0 auto;
}
.run-card.status-error .run-icon {
  background: linear-gradient(135deg, #f76c6c, #f0b455) !important;
  box-shadow: 0 6px 14px -8px rgba(247, 108, 108, 0.55),
              inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}
.run-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}
.run-name {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--color-foreground, #ffffff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-slug {
  font-size: 10.5px;
  line-height: 1.2;
  color: var(--color-foreground-subtle, #8c93a1);
  font-family: var(--wf-font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-stats {
  display: inline-flex;
  gap: 6px;
  flex-shrink: 0;
}
.run-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10.5px;
  color: var(--color-foreground-muted, #c4cad4);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  font-variant-numeric: tabular-nums;
}
.run-bar {
  grid-column: 1 / -1;
  margin-top: 2px;
  height: 3px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  overflow: hidden;
}
.run-bar-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  transition: width 0.25s ease;
}

/* ---------- expanded body ---------- */
.run-body {
  border-top: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  background: rgba(15, 17, 23, 0.55);
}
.run-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
}
.run-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  border: none;
  background: transparent;
  color: var(--color-foreground-muted, #c4cad4);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.01em;
  cursor: pointer;
  border-radius: 7px;
  transition: color 0.15s ease, background 0.15s ease;
}
.run-tab:hover { background: rgba(255, 255, 255, 0.04); }
.run-tab.active {
  color: var(--color-foreground, #ffffff);
  background: rgba(92, 141, 255, 0.14);
}
.run-tab.danger.active { background: rgba(247, 108, 108, 0.16); color: #f8c5c5; }
.run-tab-pill {
  font-size: 9.5px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-foreground-muted, #c4cad4);
}
.run-tab-spacer { flex: 1; }
.run-copy {
  display: grid;
  place-items: center;
  width: 24px;
  height: 22px;
  border-radius: 6px;
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  background: transparent;
  color: var(--color-foreground-muted, #c4cad4);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.run-copy:hover {
  color: var(--color-foreground, #ffffff);
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(92, 141, 255, 0.35);
}

/* ---------- output tab ---------- */
.run-output {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px 12px;
}
.run-items {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.run-items-label {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-foreground-subtle, #8c93a1);
  margin-right: 4px;
}
.run-item {
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  background: rgba(255, 255, 255, 0.03);
  color: var(--color-foreground-muted, #c4cad4);
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-family: var(--wf-font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.run-item:hover { color: #ffffff; border-color: rgba(92, 141, 255, 0.35); }
.run-item.active {
  color: #ffffff;
  background: rgba(92, 141, 255, 0.18);
  border-color: rgba(92, 141, 255, 0.45);
}

/* ---------- json blocks ---------- */
.run-json {
  margin: 0;
  padding: 10px 12px;
  max-height: 280px;
  overflow: auto;
  font-size: 11.5px;
  line-height: 1.5;
  font-family: var(--wf-font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  background: rgba(10, 12, 18, 0.85);
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  border-radius: 8px;
  color: #e0e4ec;
  white-space: pre;
  scrollbar-width: thin;
  scrollbar-color: rgba(92, 141, 255, 0.3) transparent;
}
.run-json :deep(.jk)   { color: #8fb8ff; }
.run-json :deep(.js)   { color: #9ae6b4; }
.run-json :deep(.jn)   { color: #f0b455; }
.run-json :deep(.jb)   { color: #f76cc6; font-weight: 600; }
.run-json :deep(.jnull) { color: #6c7383; font-style: italic; }

.run-errmsg {
  display: flex;
  gap: 8px;
  padding: 12px;
  color: #f8c5c5;
}
.run-errmsg pre {
  margin: 0;
  flex: 1;
  font-size: 11.5px;
  line-height: 1.5;
  font-family: var(--wf-font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  background: rgba(247, 108, 108, 0.08);
  border: 1px solid rgba(247, 108, 108, 0.3);
  border-radius: 8px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
  color: #f8c5c5;
}

.run-kv { padding: 10px 14px 14px; }
.run-kv dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 16px;
  margin: 0;
  font-size: 12px;
}
.run-kv dt {
  color: var(--color-foreground-subtle, #8c93a1);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding-top: 2px;
}
.run-kv dd {
  margin: 0;
  color: var(--color-foreground-muted, #c4cad4);
  word-break: break-all;
}
.run-kv dd.mono {
  font-family: var(--wf-font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  font-size: 11.5px;
  color: #e0e4ec;
}
</style>
