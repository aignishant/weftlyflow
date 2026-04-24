<script setup lang="ts">
// Bottom drawer that shows the last run's status + per-node run data.
//
// Each row is a collapsible card: click the header to expand the JSON
// sample for that node. Errors always render the message prominently.

import { AlertCircle, CheckCircle2, ChevronRight, Clock, Play } from "lucide-vue-next";
import { computed, ref } from "vue";

import Badge from "@/components/ui/Badge.vue";
import Button from "@/components/ui/Button.vue";
import { cn } from "@/lib/utils";
import type { ExecutionDetail } from "@/types/api";

const props = defineProps<{
  execution: ExecutionDetail | null;
  running: boolean;
  errorMessage: string | null;
}>();

const emit = defineEmits<{
  (event: "run"): void;
}>();

type NodeSummary = {
  nodeId: string;
  status: "success" | "error" | "disabled" | "unknown";
  items: number;
  durationMs: number;
  sampleJson: string;
  errorMessage: string | null;
};

const expanded = ref<Record<string, boolean>>({});

const nodeSummaries = computed<NodeSummary[]>(() => {
  if (!props.execution) return [];
  return Object.entries(props.execution.run_data).map(([nodeId, runs]) => {
    const last = runs[runs.length - 1];
    const ports = last?.items ?? [];
    const flat = ports.flat();
    const sample = flat[0]?.json ?? {};
    return {
      nodeId,
      status: (last?.status ?? "unknown") as NodeSummary["status"],
      items: flat.length,
      durationMs: last?.execution_time_ms ?? 0,
      sampleJson: JSON.stringify(sample, null, 2),
      errorMessage: last?.error?.message ?? null,
    };
  });
});

const totalDurationMs = computed(() => {
  if (!props.execution?.finished_at) return null;
  const start = new Date(props.execution.started_at).getTime();
  const end = new Date(props.execution.finished_at).getTime();
  return Number.isFinite(end - start) ? end - start : null;
});

type BadgeVariant = "success" | "danger" | "muted" | "accent";

function statusBadgeVariant(status: string): BadgeVariant {
  if (status === "success") return "success";
  if (status === "error") return "danger";
  if (status === "running") return "accent";
  return "muted";
}

function toggleExpanded(nodeId: string): void {
  expanded.value = { ...expanded.value, [nodeId]: !expanded.value[nodeId] };
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}
</script>

<template>
  <section
    class="flex flex-col max-h-[50%] overflow-y-auto border-t border-[var(--color-border-subtle)] bg-[var(--color-surface)] px-4 py-3 gap-2"
    data-testid="execution-panel"
  >
    <header class="flex items-center gap-2">
      <h3 class="text-sm font-semibold text-[var(--color-foreground)] m-0">
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
        v-if="totalDurationMs !== null && !running"
        class="inline-flex items-center gap-1 text-[11px] text-[var(--color-foreground-subtle)] font-mono"
      >
        <Clock class="h-3 w-3" />
        {{ formatDuration(totalDurationMs) }}
      </span>

      <div class="flex-1" />

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
    </header>

    <div
      v-if="errorMessage"
      class="flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--color-danger)] bg-[color-mix(in_srgb,var(--color-danger)_10%,transparent)] px-3 py-2 text-sm text-[var(--color-danger)]"
    >
      <AlertCircle class="h-4 w-4 mt-0.5 shrink-0" />
      <span>{{ errorMessage }}</span>
    </div>

    <div
      v-if="!execution && !running && !errorMessage"
      class="flex flex-col items-center justify-center py-8 text-center text-[var(--color-foreground-subtle)]"
    >
      <Play class="h-6 w-6 mb-2 opacity-60" />
      <p class="text-sm m-0">
        No runs yet.
      </p>
      <p class="text-xs mt-1 m-0">
        Click Execute to run the workflow with a single empty item.
      </p>
    </div>

    <div
      v-if="execution"
      class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3"
      data-testid="run-data"
    >
      <div
        v-for="row in nodeSummaries"
        :key="row.nodeId"
        class="rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-bg)] overflow-hidden"
      >
        <button
          type="button"
          class="w-full flex items-center gap-2 px-3 py-2 hover:bg-[var(--color-surface-2)] transition-colors text-left"
          @click="toggleExpanded(row.nodeId)"
        >
          <ChevronRight
            :class="cn(
              'h-3 w-3 text-[var(--color-foreground-subtle)] transition-transform shrink-0',
              expanded[row.nodeId] && 'rotate-90',
            )"
          />
          <CheckCircle2
            v-if="row.status === 'success'"
            class="h-3.5 w-3.5 text-[var(--color-success)] shrink-0"
          />
          <AlertCircle
            v-else-if="row.status === 'error'"
            class="h-3.5 w-3.5 text-[var(--color-danger)] shrink-0"
          />
          <span
            v-else
            class="h-2 w-2 rounded-full bg-[var(--color-foreground-subtle)] shrink-0"
          />
          <span class="text-[13px] font-medium text-[var(--color-foreground)] truncate flex-1">
            {{ row.nodeId }}
          </span>
          <span class="text-[10px] font-mono text-[var(--color-foreground-subtle)] shrink-0">
            {{ row.items }} item{{ row.items === 1 ? "" : "s" }} · {{ formatDuration(row.durationMs) }}
          </span>
        </button>

        <div
          v-if="expanded[row.nodeId]"
          class="border-t border-[var(--color-border-subtle)] p-3"
        >
          <p
            v-if="row.errorMessage"
            class="text-xs text-[var(--color-danger)] mb-2 m-0"
          >
            {{ row.errorMessage }}
          </p>
          <pre class="text-[11px] font-mono text-[var(--color-foreground-muted)] bg-[var(--color-surface-2)] rounded-[var(--radius-sm)] p-2 overflow-x-auto m-0 max-h-60">{{ row.sampleJson }}</pre>
        </div>
      </div>
    </div>
  </section>
</template>
