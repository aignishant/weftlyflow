<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { extractErrorMessage } from "@/api/client";
import { useNodeTypesStore } from "@/stores/nodeTypes";
import { useWorkflowsStore } from "@/stores/workflows";

const store = useWorkflowsStore();
const nodeTypes = useNodeTypesStore();
const router = useRouter();

const creating = ref(false);
const newName = ref("");
const createError = ref<string | null>(null);

onMounted(async () => {
  await store.fetchAll();
  await nodeTypes.loadOnce();
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
</script>

<template>
  <div class="home">
    <section class="wf-card create">
      <h2>Create a workflow</h2>
      <form class="wf-row" @submit.prevent="createWorkflow">
        <input
          v-model="newName"
          data-testid="workflow-name"
          placeholder="My new workflow"
          required
        />
        <button
          type="submit"
          class="primary"
          data-testid="workflow-create"
          :disabled="creating || !newName.trim()"
        >
          {{ creating ? "Creating…" : "Create" }}
        </button>
      </form>
      <p v-if="createError" class="error">{{ createError }}</p>
    </section>

    <section class="wf-card list">
      <h2>Workflows</h2>
      <p v-if="store.loading" class="muted">Loading…</p>
      <p v-else-if="store.items.length === 0" class="muted">
        No workflows yet. Create one above.
      </p>
      <table v-else data-testid="workflow-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Nodes</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="wf in store.items" :key="wf.id" :data-workflow-id="wf.id">
            <td>
              <RouterLink
                :to="{ name: 'editor', params: { id: wf.id } }"
                class="wf-link"
                :data-testid="`workflow-open-${wf.id}`"
                >{{ wf.name }}</RouterLink
              >
            </td>
            <td>
              <span class="wf-badge" :class="wf.active ? 'success' : 'waiting'">
                {{ wf.active ? "active" : "inactive" }}
              </span>
            </td>
            <td>{{ wf.nodes.length }}</td>
            <td class="actions">
              <button class="danger" @click="onDelete(wf.id, wf.name)">
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.home {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
h2 {
  margin: 0 0 12px 0;
  font-size: 16px;
}
.create form {
  display: flex;
  gap: 8px;
}
.create input {
  flex: 1;
}
.muted {
  color: var(--wf-text-muted);
  margin: 0;
}
.actions {
  text-align: right;
}
.wf-link {
  color: var(--wf-text);
  font-weight: 500;
}
.wf-link:hover {
  color: var(--wf-accent);
}
.error {
  color: var(--wf-danger);
  margin: 8px 0 0 0;
}
</style>
