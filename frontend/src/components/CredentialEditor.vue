<script setup lang="ts">
// Modal form for creating or editing a credential. Uses the selected
// credential-type's properties as the field schema. Plaintext is cleared
// from memory once the caller closes the modal.

import { AlertCircle, KeyRound, ShieldCheck, X } from "lucide-vue-next";
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
const formError = ref<string | null>(null);

watch(
  () => value.value.type,
  (next, prev) => {
    if (next !== prev) {
      // Reset data when the type changes so stale fields don't leak.
      value.value.data = {};
      formError.value = null;
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
  formError.value = null;
}

function close(): void {
  emit("close");
}

async function submit(): Promise<void> {
  if (submitting.value) {
    return;
  }
  if (!value.value.name.trim()) {
    formError.value = "Name is required.";
    return;
  }
  if (!value.value.type) {
    formError.value = "Pick a credential type.";
    return;
  }
  const required = (selectedType.value?.properties ?? []).filter((p) => p.required);
  const missing = required.find((p) => {
    const v = value.value.data[p.name];
    return v === undefined || v === null || v === "";
  });
  if (missing) {
    formError.value = `${missing.display_name} is required.`;
    return;
  }
  submitting.value = true;
  try {
    formError.value = null;
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

const headingLabel = computed(() => (value.value.id ? "Edit credential" : "Create credential"));
const subLabel = computed(() =>
  value.value.id
    ? "Update the secret values stored for this credential."
    : "Store OAuth tokens or API keys encrypted at rest.",
);
</script>

<template>
  <div
    class="backdrop"
    @click.self="close"
  >
    <form
      class="modal"
      data-testid="credential-modal"
      @submit.prevent="submit"
    >
      <header class="m-head">
        <div class="m-head-main">
          <span class="m-logo">
            <ShieldCheck :size="18" />
          </span>
          <div class="m-head-text">
            <h2>{{ headingLabel }}</h2>
            <p class="m-sub">
              {{ subLabel }}
            </p>
          </div>
        </div>
        <button
          type="button"
          class="m-close"
          aria-label="Close"
          @click="close"
        >
          <X :size="16" />
        </button>
      </header>

      <div
        v-if="formError"
        class="m-alert"
        role="alert"
      >
        <span class="m-alert-icon">
          <AlertCircle :size="16" />
        </span>
        <div class="m-alert-body">
          <span class="m-alert-title">Check the form</span>
          <span class="m-alert-msg">{{ formError }}</span>
        </div>
        <button
          type="button"
          class="m-alert-close"
          aria-label="Dismiss"
          @click="formError = null"
        >
          ×
        </button>
      </div>

      <div class="m-body">
        <div class="m-field">
          <label for="cred-name">Name</label>
          <input
            id="cred-name"
            v-model="value.name"
            data-testid="cred-name"
            placeholder="e.g. Production Slack bot"
            required
          >
        </div>

        <div class="m-field">
          <label for="cred-type">Type</label>
          <div class="m-select-wrap">
            <KeyRound
              :size="14"
              class="m-select-icon"
            />
            <select
              id="cred-type"
              v-model="value.type"
              data-testid="cred-type"
              :disabled="Boolean(value.id)"
            >
              <option
                v-for="t in types"
                :key="t.slug"
                :value="t.slug"
              >
                {{ t.display_name }}
              </option>
            </select>
          </div>
        </div>

        <template v-if="selectedType">
          <div
            v-for="prop in selectedType.properties"
            :key="prop.name"
            class="m-field"
          >
            <label>
              {{ prop.display_name }}
              <span
                v-if="prop.required"
                class="m-required"
              >*</span>
            </label>
            <input
              v-if="prop.type === 'number'"
              type="number"
              :value="fieldValue(prop)"
              :data-testid="`cred-field-${prop.name}`"
              @input="updateField(prop, Number(($event.target as HTMLInputElement).value))"
            >
            <input
              v-else
              :type="prop.type_options?.password ? 'password' : 'text'"
              :value="fieldValue(prop)"
              :data-testid="`cred-field-${prop.name}`"
              @input="updateField(prop, ($event.target as HTMLInputElement).value)"
            >
            <p
              v-if="prop.description"
              class="m-hint"
            >
              {{ prop.description }}
            </p>
          </div>
        </template>
      </div>

      <div class="m-actions">
        <button
          type="button"
          class="m-btn ghost"
          @click="close"
        >
          Cancel
        </button>
        <button
          class="m-btn primary"
          type="submit"
          data-testid="cred-save"
          :disabled="submitting"
        >
          <ShieldCheck :size="14" />
          <span>{{ value.id ? "Save credential" : "Create credential" }}</span>
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background:
    radial-gradient(800px 500px at 50% 0%, rgba(92, 141, 255, 0.08), transparent 60%),
    rgba(4, 6, 12, 0.72);
  backdrop-filter: blur(6px);
  display: grid;
  place-items: center;
  z-index: 100;
  animation: m-fade 0.15s ease-out;
}
@keyframes m-fade {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.modal {
  position: relative;
  width: 520px;
  max-width: calc(100vw - 32px);
  max-height: 86vh;
  overflow-y: auto;
  padding: 20px 22px 20px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background:
    radial-gradient(600px 220px at 0% 0%, rgba(92, 141, 255, 0.14), transparent 65%),
    radial-gradient(500px 240px at 100% 100%, rgba(139, 92, 255, 0.12), transparent 60%),
    linear-gradient(180deg, rgba(28, 31, 44, 0.96), rgba(22, 25, 36, 0.96));
  box-shadow:
    0 30px 80px -20px rgba(0, 0, 0, 0.7),
    0 0 0 1px rgba(255, 255, 255, 0.04);
  animation: m-rise 0.2s ease-out;
}
.modal::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 16px;
  padding: 1px;
  background: linear-gradient(135deg, rgba(92, 141, 255, 0.55), transparent 55%, rgba(139, 92, 255, 0.45));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
  opacity: 0.7;
}
@keyframes m-rise {
  from { opacity: 0; transform: translateY(6px) scale(0.985); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

/* header */
.m-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
  position: relative;
}
.m-head-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.m-logo {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  color: #0f1117;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  box-shadow: 0 12px 26px -14px rgba(92, 141, 255, 0.7),
              inset 0 0 0 1px rgba(255, 255, 255, 0.18);
  flex: 0 0 auto;
}
.m-head-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.m-head-text h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  background: linear-gradient(135deg, #c8d3ee, #8b5cff);
  -webkit-background-clip: text;
          background-clip: text;
  color: transparent;
  letter-spacing: -0.005em;
}
.m-sub {
  margin: 0;
  font-size: 12px;
  color: var(--wf-text-muted, #8891a7);
  line-height: 1.4;
}
.m-close {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--wf-text-muted, #8891a7);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
  flex: 0 0 auto;
}
.m-close:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.08);
}

/* alert */
.m-alert {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  margin: 0 0 14px 0;
  border-radius: 12px;
  background:
    radial-gradient(400px 120px at 0% 0%, rgba(247, 108, 108, 0.15), transparent 70%),
    linear-gradient(180deg, rgba(60, 22, 28, 0.65), rgba(40, 18, 22, 0.7));
  border: 1px solid rgba(247, 108, 108, 0.38);
  position: relative;
  overflow: hidden;
  animation: m-alert-in 0.2s ease-out;
}
.m-alert::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(247, 108, 108, 0.18), transparent 35%);
  pointer-events: none;
}
@keyframes m-alert-in {
  from { opacity: 0; transform: translateY(-3px); }
  to   { opacity: 1; transform: translateY(0); }
}
.m-alert-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  color: #0f1117;
  background: linear-gradient(135deg, #f76c6c, #f0b455);
  box-shadow: 0 8px 18px -10px rgba(247, 108, 108, 0.6),
              inset 0 0 0 1px rgba(255, 255, 255, 0.2);
  flex: 0 0 auto;
  position: relative;
  z-index: 1;
}
.m-alert-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
  position: relative;
  z-index: 1;
}
.m-alert-title {
  font-size: 12.5px;
  font-weight: 700;
  color: #ffd4d4;
  letter-spacing: 0.01em;
}
.m-alert-msg {
  font-size: 12.5px;
  color: #f0b0b0;
  line-height: 1.5;
  word-break: break-word;
}
.m-alert-close {
  border: none;
  background: transparent;
  color: #f0b0b0;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
  transition: color 0.15s ease;
  position: relative;
  z-index: 1;
}
.m-alert-close:hover { color: #ffffff; }

/* body fields */
.m-body { display: flex; flex-direction: column; gap: 12px; }
.m-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.m-field label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--wf-text-muted, #8891a7);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.m-required { color: #f76c6c; margin-left: 2px; }
.m-field input,
.m-field select {
  width: 100%;
  background: rgba(15, 17, 23, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--wf-text, #e6ebf6);
  padding: 9px 11px;
  border-radius: 9px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}
.m-field input::placeholder { color: rgba(150, 160, 180, 0.5); }
.m-field input:focus,
.m-field select:focus {
  border-color: rgba(139, 92, 255, 0.55);
  background: rgba(15, 17, 23, 0.82);
  box-shadow: 0 0 0 3px rgba(139, 92, 255, 0.18);
}
.m-field select:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.m-select-wrap {
  position: relative;
}
.m-select-icon {
  position: absolute;
  left: 11px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--wf-text-muted, #8891a7);
  pointer-events: none;
}
.m-select-wrap select {
  padding-left: 32px;
  appearance: none;
  background-image:
    linear-gradient(45deg, transparent 50%, var(--wf-text-muted, #8891a7) 50%),
    linear-gradient(135deg, var(--wf-text-muted, #8891a7) 50%, transparent 50%);
  background-position:
    calc(100% - 14px) 50%,
    calc(100% - 9px) 50%;
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
}
.m-hint {
  color: var(--wf-text-muted, #8891a7);
  font-size: 11.5px;
  line-height: 1.45;
  margin: 0;
}

/* actions */
.m-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.m-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
  padding: 9px 14px;
  border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: transform 0.12s ease, filter 0.15s ease, background 0.15s ease;
}
.m-btn.ghost {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: var(--wf-text, #e6ebf6);
}
.m-btn.ghost:hover {
  background: rgba(255, 255, 255, 0.07);
}
.m-btn.primary {
  color: #0f1117;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  box-shadow: 0 12px 28px -12px rgba(92, 141, 255, 0.65),
              inset 0 0 0 1px rgba(255, 255, 255, 0.15);
}
.m-btn.primary:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.06);
}
.m-btn.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
