<script setup lang="ts">
// Generic parameter-form generator driven by NodeType.properties. Supports
// the MVP set of field types: string, number, boolean, options, json.
// Credential slots render as a dropdown selecting a CredentialSummary.

import { computed } from "vue";

import type {
  CredentialSummary,
  NodeProperty,
  NodeType,
  WorkflowNode,
} from "@/types/api";

const props = defineProps<{
  node: WorkflowNode;
  nodeType: NodeType | undefined;
  credentials: CredentialSummary[];
}>();

const emit = defineEmits<{
  (event: "update-name", value: string): void;
  (event: "update-parameter", name: string, value: unknown): void;
  (event: "update-credential", slot: string, credentialId: string | null): void;
  (event: "delete"): void;
}>();

const nameModel = computed({
  get: () => props.node.name,
  set: (value: string) => emit("update-name", value),
});

function paramValue(prop: NodeProperty): unknown {
  const value = props.node.parameters?.[prop.name];
  if (value !== undefined) {
    return value;
  }
  return prop.default ?? null;
}

function onInput(prop: NodeProperty, raw: string | number | boolean): void {
  let coerced: unknown = raw;
  if (prop.type === "number") {
    coerced = raw === "" ? null : Number(raw);
  }
  emit("update-parameter", prop.name, coerced);
}

function onJsonInput(prop: NodeProperty, raw: string): void {
  // Store raw text until it parses cleanly — avoids clobbering keystrokes.
  try {
    emit("update-parameter", prop.name, raw === "" ? null : JSON.parse(raw));
  } catch {
    emit("update-parameter", prop.name, raw);
  }
}

function asJsonString(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

function credentialsForSlot(slotTypes: string[]): CredentialSummary[] {
  return props.credentials.filter((c) => slotTypes.includes(c.type));
}

function currentCredentialFor(slotName: string): string {
  return props.node.credentials?.[slotName] ?? "";
}
</script>

<template>
  <div
    class="form"
    data-testid="node-form"
  >
    <div class="heading wf-row">
      <div class="stack-full">
        <label>Name</label>
        <input
          v-model="nameModel"
          data-testid="node-name"
        >
      </div>
      <button
        class="danger"
        data-testid="node-delete"
        @click="emit('delete')"
      >
        Delete
      </button>
    </div>
    <p class="meta">
      {{ node.type }}
    </p>

    <template v-if="nodeType">
      <section
        v-if="(nodeType.credentials || []).length > 0"
        class="group"
      >
        <h4>Credentials</h4>
        <div
          v-for="slot in nodeType.credentials"
          :key="slot.name"
          class="field"
        >
          <label>{{ slot.name }}</label>
          <select
            :value="currentCredentialFor(slot.name)"
            :data-testid="`node-credential-${slot.name}`"
            @change="
              emit(
                'update-credential',
                slot.name,
                ($event.target as HTMLSelectElement).value || null,
              )
            "
          >
            <option value="">
              — none —
            </option>
            <option
              v-for="cred in credentialsForSlot(slot.credential_types)"
              :key="cred.id"
              :value="cred.id"
            >
              {{ cred.name }} ({{ cred.type }})
            </option>
          </select>
        </div>
      </section>

      <section
        v-if="nodeType.properties.length > 0"
        class="group"
      >
        <h4>Parameters</h4>
        <div
          v-for="prop in nodeType.properties"
          :key="prop.name"
          class="field"
        >
          <label>
            {{ prop.display_name }}
            <span
              v-if="prop.required"
              class="required"
            >*</span>
          </label>
          <template v-if="prop.type === 'boolean'">
            <input
              type="checkbox"
              :checked="Boolean(paramValue(prop))"
              :data-testid="`node-param-${prop.name}`"
              @change="onInput(prop, ($event.target as HTMLInputElement).checked)"
            >
          </template>
          <template v-else-if="prop.type === 'options'">
            <select
              :value="paramValue(prop) ?? ''"
              :data-testid="`node-param-${prop.name}`"
              @change="onInput(prop, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-if="!prop.required"
                value=""
              >
                — default —
              </option>
              <option
                v-for="opt in prop.options || []"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </option>
            </select>
          </template>
          <template v-else-if="prop.type === 'number'">
            <input
              type="number"
              :value="paramValue(prop) ?? ''"
              :data-testid="`node-param-${prop.name}`"
              @input="onInput(prop, ($event.target as HTMLInputElement).value)"
            >
          </template>
          <template v-else-if="prop.type === 'json'">
            <textarea
              :value="asJsonString(paramValue(prop))"
              :data-testid="`node-param-${prop.name}`"
              spellcheck="false"
              @input="onJsonInput(prop, ($event.target as HTMLTextAreaElement).value)"
            />
          </template>
          <template v-else>
            <input
              :type="prop.type_options?.password ? 'password' : 'text'"
              :value="paramValue(prop) ?? ''"
              :placeholder="prop.placeholder ?? ''"
              :data-testid="`node-param-${prop.name}`"
              @input="onInput(prop, ($event.target as HTMLInputElement).value)"
            >
          </template>
          <p
            v-if="prop.description"
            class="hint"
          >
            {{ prop.description }}
          </p>
        </div>
      </section>
    </template>
    <p
      v-else
      class="meta"
    >
      Unknown node type — install the matching plugin.
    </p>
  </div>
</template>

<style scoped>
.form {
  padding: 16px;
  overflow-y: auto;
}
.heading {
  align-items: flex-end;
}
.stack-full {
  flex: 1;
}
.meta {
  color: var(--wf-text-muted);
  font-family: var(--wf-font-mono);
  font-size: 11px;
  margin: 4px 0 16px 0;
}
.group {
  border-top: 1px solid var(--wf-border);
  padding-top: 12px;
  margin-top: 12px;
}
h4 {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: var(--wf-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.field {
  margin-bottom: 12px;
}
.required {
  color: var(--wf-danger);
  margin-left: 2px;
}
.hint {
  color: var(--wf-text-muted);
  font-size: 11px;
  margin: 4px 0 0 0;
}
</style>
