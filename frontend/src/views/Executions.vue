<script setup lang="ts">
import { onMounted } from "vue";

import { useExecutionsStore } from "@/stores/executions";

const store = useExecutionsStore();

onMounted(async () => {
  await store.fetchList();
});

function formatTime(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString();
}
</script>

<template>
  <div class="executions">
    <section class="wf-card">
      <header class="wf-row">
        <h2>Executions</h2>
        <div class="spacer" />
        <button @click="store.fetchList()">
          Refresh
        </button>
      </header>
      <p
        v-if="store.loading"
        class="muted"
      >
        Loading…
      </p>
      <p
        v-else-if="store.items.length === 0"
        class="muted"
      >
        No executions yet — run a workflow to see its history here.
      </p>
      <table
        v-else
        data-testid="executions-table"
      >
        <thead>
          <tr>
            <th>Id</th>
            <th>Workflow</th>
            <th>Mode</th>
            <th>Status</th>
            <th>Started</th>
            <th>Finished</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in store.items"
            :key="row.id"
          >
            <td>
              <RouterLink
                :to="{ name: 'execution-detail', params: { id: row.id } }"
                class="id"
              >
                {{ row.id }}
              </RouterLink>
            </td>
            <td class="mono">
              {{ row.workflow_id }}
            </td>
            <td>{{ row.mode }}</td>
            <td>
              <span
                class="wf-badge"
                :class="row.status"
              >{{ row.status }}</span>
            </td>
            <td>{{ formatTime(row.started_at) }}</td>
            <td>{{ formatTime(row.finished_at) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.executions {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}
h2 {
  margin: 0;
  font-size: 16px;
}
.mono {
  font-family: var(--wf-font-mono);
  font-size: 12px;
}
.id {
  font-family: var(--wf-font-mono);
  font-size: 12px;
  color: var(--wf-accent);
}
.muted {
  color: var(--wf-text-muted);
  margin: 12px 0 0 0;
}
</style>
