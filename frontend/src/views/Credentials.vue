<script setup lang="ts">
import { onMounted, ref } from "vue";

import { extractErrorMessage } from "@/api/client";
import CredentialEditor from "@/components/CredentialEditor.vue";
import { CREDENTIALS_TOUR, startTour } from "@/lib/tour";
import { useCredentialsStore } from "@/stores/credentials";

interface EditingValue {
  id?: string;
  name: string;
  type: string;
  data: Record<string, unknown>;
}

const store = useCredentialsStore();

const editing = ref<EditingValue | null>(null);
const actionError = ref<string | null>(null);
const testResults = ref<Record<string, { ok: boolean; message: string }>>({});

onMounted(async () => {
  await store.fetchAll();
  setTimeout(() => startTour(CREDENTIALS_TOUR), 400);
});

function openNew(): void {
  editing.value = {
    name: "",
    type: store.types[0]?.slug ?? "weftlyflow.bearer_token",
    data: {},
  };
}

function closeEditor(): void {
  editing.value = null;
}

async function onSubmit(value: EditingValue): Promise<void> {
  actionError.value = null;
  try {
    if (value.id) {
      await store.update(value.id, { name: value.name, data: value.data });
    } else {
      await store.create({ name: value.name, type: value.type, data: value.data });
    }
    closeEditor();
  } catch (err) {
    actionError.value = extractErrorMessage(err);
  }
}

async function onDelete(id: string, name: string): Promise<void> {
  if (!window.confirm(`Delete credential "${name}"?`)) {
    return;
  }
  try {
    await store.remove(id);
  } catch (err) {
    actionError.value = extractErrorMessage(err);
  }
}

async function onTest(id: string): Promise<void> {
  try {
    testResults.value = { ...testResults.value, [id]: await store.test(id) };
  } catch (err) {
    actionError.value = extractErrorMessage(err);
  }
}
</script>

<template>
  <div class="credentials">
    <section class="wf-card">
      <header class="wf-row">
        <h2>Credentials</h2>
        <div class="spacer" />
        <button
          class="primary"
          data-testid="new-credential"
          @click="openNew"
        >
          New credential
        </button>
      </header>
      <p
        v-if="actionError"
        class="error"
      >
        {{ actionError }}
      </p>
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
        No credentials yet. Click “New credential” to add one.
      </p>
      <table
        v-else
        data-testid="credentials-table"
      >
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Test</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in store.items"
            :key="row.id"
            :data-credential-id="row.id"
          >
            <td>{{ row.name }}</td>
            <td class="mono">
              {{ row.type }}
            </td>
            <td>
              <button @click="onTest(row.id)">
                Test
              </button>
              <span
                v-if="testResults[row.id]"
                class="wf-badge"
                :class="testResults[row.id].ok ? 'success' : 'error'"
              >
                {{ testResults[row.id].ok ? "ok" : testResults[row.id].message }}
              </span>
            </td>
            <td class="actions">
              <button
                class="danger"
                @click="onDelete(row.id, row.name)"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <CredentialEditor
      v-if="editing"
      :types="store.types"
      :initial="editing"
      @close="closeEditor"
      @submit="onSubmit"
    />
  </div>
</template>

<style scoped>
.credentials {
  max-width: 960px;
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
.actions {
  text-align: right;
}
.muted {
  color: var(--wf-text-muted);
  margin: 12px 0 0 0;
}
.error {
  color: var(--wf-danger);
  margin: 8px 0;
}
.wf-badge {
  margin-left: 8px;
}
</style>
