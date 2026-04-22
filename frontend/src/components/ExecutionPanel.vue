<script setup lang="ts">
// Bottom drawer that shows the last run's status + per-node run data.

import { computed } from "vue";

import type { ExecutionDetail } from "@/types/api";

const props = defineProps<{
  execution: ExecutionDetail | null;
  running: boolean;
  errorMessage: string | null;
}>();

const emit = defineEmits<{
  (event: "run"): void;
}>();

const nodeSummaries = computed(() => {
  if (!props.execution) {
    return [] as { nodeId: string; status: string; items: number; sampleJson: string }[];
  }
  return Object.entries(props.execution.run_data).map(([nodeId, runs]) => {
    const last = runs[runs.length - 1];
    const ports = last?.items ?? [];
    const flat = ports.flat();
    const sample = flat[0]?.json ?? {};
    return {
      nodeId,
      status: last?.status ?? "unknown",
      items: flat.length,
      sampleJson: JSON.stringify(sample, null, 2),
    };
  });
});
</script>

<template>
  <section class="panel" data-testid="execution-panel">
    <header>
      <h3>Last execution</h3>
      <button
        class="primary"
        data-testid="execute-button"
        :disabled="running"
        @click="emit('run')"
      >
        {{ running ? "Running…" : "Execute" }}
      </button>
    </header>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    <p v-if="!execution && !running && !errorMessage" class="muted">
      Click Execute to run the workflow with a single empty item.
    </p>
    <div v-if="execution" class="summary">
      <span class="wf-badge" :class="execution.status">
        {{ execution.status }}
      </span>
      <span class="id">{{ execution.id }}</span>
    </div>
    <div v-if="execution" class="grid" data-testid="run-data">
      <div v-for="row in nodeSummaries" :key="row.nodeId" class="wf-card node">
        <header>
          <strong>{{ row.nodeId }}</strong>
          <span class="wf-badge" :class="row.status">{{ row.status }}</span>
        </header>
        <p class="muted">{{ row.items }} item(s)</p>
        <pre class="wf-json">{{ row.sampleJson }}</pre>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  border-top: 1px solid var(--wf-border);
  background: var(--wf-bg-elevated);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 50%;
  overflow-y: auto;
}
.panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel h3 {
  margin: 0;
  font-size: 14px;
}
.summary {
  display: flex;
  gap: 8px;
  align-items: center;
}
.summary .id {
  color: var(--wf-text-muted);
  font-family: var(--wf-font-mono);
  font-size: 12px;
}
.error {
  color: var(--wf-danger);
  margin: 0;
}
.muted {
  color: var(--wf-text-muted);
  margin: 0;
  font-size: 12px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-top: 8px;
}
.node header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
</style>
