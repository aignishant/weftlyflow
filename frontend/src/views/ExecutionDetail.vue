<script setup lang="ts">
import { computed, onMounted, watch } from "vue";

import { useExecutionsStore } from "@/stores/executions";

const props = defineProps<{ id: string }>();

const store = useExecutionsStore();

onMounted(async () => {
  await store.fetchOne(props.id);
});

watch(
  () => props.id,
  async (newId) => {
    await store.fetchOne(newId);
  },
);

const execution = computed(() => store.current);

function asJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
</script>

<template>
  <div class="detail">
    <section
      v-if="execution"
      class="wf-card"
    >
      <header class="wf-row">
        <h2>{{ execution.id }}</h2>
        <span
          class="wf-badge"
          :class="execution.status"
        >{{ execution.status }}</span>
        <div class="spacer" />
        <RouterLink :to="{ name: 'executions' }">
          ← Back to list
        </RouterLink>
      </header>
      <dl class="meta">
        <dt>Workflow</dt>
        <dd class="mono">
          {{ execution.workflow_id }}
        </dd>
        <dt>Mode</dt>
        <dd>{{ execution.mode }}</dd>
        <dt>Started</dt>
        <dd>{{ new Date(execution.started_at).toLocaleString() }}</dd>
        <dt>Finished</dt>
        <dd>
          {{ execution.finished_at
            ? new Date(execution.finished_at).toLocaleString()
            : "—" }}
        </dd>
      </dl>
    </section>

    <section
      v-if="execution"
      class="wf-card runs"
      data-testid="run-data-detail"
    >
      <h3>Run data</h3>
      <details
        v-for="[nodeId, runs] in Object.entries(execution.run_data)"
        :key="nodeId"
        open
      >
        <summary>
          <strong>{{ nodeId }}</strong>
          <span
            class="wf-badge"
            :class="runs[runs.length - 1]?.status ?? 'waiting'"
          >
            {{ runs[runs.length - 1]?.status ?? "pending" }}
          </span>
        </summary>
        <div
          v-for="(run, idx) in runs"
          :key="idx"
          class="run"
        >
          <p class="muted">
            Run #{{ idx + 1 }} — {{ run.execution_time_ms }} ms
          </p>
          <pre class="wf-json">{{ asJson(run.items) }}</pre>
        </div>
      </details>
    </section>

    <p
      v-if="!execution && store.loading"
      class="muted"
    >
      Loading…
    </p>
    <p
      v-if="store.error"
      class="error"
    >
      {{ store.error }}
    </p>
  </div>
</template>

<style scoped>
.detail {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
h2 {
  margin: 0;
  font-size: 16px;
  font-family: var(--wf-font-mono);
}
h3 {
  margin: 0 0 12px 0;
}
.meta {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 4px 12px;
  margin: 12px 0 0 0;
}
.meta dt {
  color: var(--wf-text-muted);
  font-size: 12px;
}
.meta dd {
  margin: 0;
}
.mono {
  font-family: var(--wf-font-mono);
  font-size: 12px;
}
.run {
  margin-top: 8px;
}
.muted {
  color: var(--wf-text-muted);
  margin: 0;
}
.error {
  color: var(--wf-danger);
  margin: 0;
}
details {
  border-top: 1px solid var(--wf-border);
  padding: 8px 0;
}
details:first-of-type {
  border-top: 0;
}
summary {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
