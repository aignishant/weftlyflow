<script setup lang="ts">
// Modal form for creating or editing a credential. Uses the selected
// credential-type's properties as the field schema. Plaintext is cleared
// from memory once the caller closes the modal.

import { computed, ref, watch } from "vue";

import type { CredentialTypeEntry, NodeProperty } from "@/types/api";

interface EditingValue {
  id?: string;
  name: string;
  type: string;
  data: Record<string, unknown>;
}

const props = defineProps<{
  types: CredentialTypeEntry[];
  initial?: EditingValue | null;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "submit", value: EditingValue): void;
}>();

const value = ref<EditingValue>({
  name: props.initial?.name ?? "",
  type: props.initial?.type ?? props.types[0]?.slug ?? "",
  data: { ...(props.initial?.data ?? {}) },
  ...(props.initial?.id ? { id: props.initial.id } : {}),
});

const selectedType = computed<CredentialTypeEntry | undefined>(() =>
  props.types.find((t) => t.slug === value.value.type),
);

const submitting = ref(false);

watch(
  () => value.value.type,
  (next, prev) => {
    if (next !== prev) {
      // Reset data when the type changes so stale fields don't leak.
      value.value.data = {};
    }
  },
);

function updateField(prop: NodeProperty, raw: string | boolean | number): void {
  const data = { ...value.value.data };
  if (raw === "" || raw === null || raw === undefined) {
    delete data[prop.name];
  } else {
    data[prop.name] = raw;
  }
  value.value.data = data;
}

function close(): void {
  emit("close");
}

async function submit(): Promise<void> {
  if (submitting.value) {
    return;
  }
  submitting.value = true;
  try {
    emit("submit", value.value);
  } finally {
    submitting.value = false;
  }
}

function fieldValue(prop: NodeProperty): string | number | boolean {
  const current = value.value.data[prop.name];
  if (current !== undefined) {
    return current as string | number | boolean;
  }
  if (prop.default !== undefined && prop.default !== null) {
    return prop.default as string | number | boolean;
  }
  return "";
}
</script>

<template>
  <div class="backdrop" @click.self="close">
    <form class="modal wf-card" data-testid="credential-modal" @submit.prevent="submit">
      <header>
        <h2>{{ value.id ? "Edit credential" : "Create credential" }}</h2>
        <button type="button" class="close" @click="close">×</button>
      </header>

      <label for="cred-name">Name</label>
      <input id="cred-name" v-model="value.name" data-testid="cred-name" required />

      <label for="cred-type">Type</label>
      <select
        id="cred-type"
        v-model="value.type"
        data-testid="cred-type"
        :disabled="Boolean(value.id)"
      >
        <option v-for="t in types" :key="t.slug" :value="t.slug">
          {{ t.display_name }}
        </option>
      </select>

      <template v-if="selectedType">
        <div v-for="prop in selectedType.properties" :key="prop.name" class="field">
          <label>
            {{ prop.display_name }}
            <span v-if="prop.required" class="required">*</span>
          </label>
          <input
            v-if="prop.type === 'number'"
            type="number"
            :value="fieldValue(prop)"
            :data-testid="`cred-field-${prop.name}`"
            @input="updateField(prop, Number(($event.target as HTMLInputElement).value))"
          />
          <input
            v-else
            :type="prop.type_options?.password ? 'password' : 'text'"
            :value="fieldValue(prop)"
            :data-testid="`cred-field-${prop.name}`"
            @input="updateField(prop, ($event.target as HTMLInputElement).value)"
          />
          <p v-if="prop.description" class="hint">{{ prop.description }}</p>
        </div>
      </template>

      <div class="wf-row buttons">
        <div class="spacer" />
        <button type="button" @click="close">Cancel</button>
        <button class="primary" type="submit" data-testid="cred-save">
          {{ value.id ? "Save" : "Create" }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: grid;
  place-items: center;
  z-index: 100;
}
.modal {
  width: 480px;
  max-height: 80vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
h2 {
  margin: 0;
  font-size: 16px;
}
.close {
  background: transparent;
  border: none;
  font-size: 20px;
  line-height: 1;
  color: var(--wf-text-muted);
  cursor: pointer;
}
.field {
  margin-top: 8px;
}
.hint {
  color: var(--wf-text-muted);
  font-size: 11px;
  margin: 4px 0 0 0;
}
.required {
  color: var(--wf-danger);
}
.buttons {
  margin-top: 12px;
}
</style>
