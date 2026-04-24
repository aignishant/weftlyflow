<script setup lang="ts">
// Rich parameter-form generator driven by NodeType.properties. Layered
// over the plain MVP form: every field now ships with an inline "e.g."
// example, tappable suggestion chips, a collapsible "more help" block
// with a longer tip, and gradient section headers. Credential slots get
// the same treatment. Supported field types: string, number, boolean,
// options, json, collection (object-as-json).

import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  HelpCircle,
  Info,
  KeyRound,
  Lightbulb,
  Plug,
  Sliders,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-vue-next";
import { computed, ref } from "vue";

import { helpFor } from "@/lib/fieldExamples";
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

const expandedTips = ref<Record<string, boolean>>({});
const collapsedSections = ref<Record<string, boolean>>({});

function toggleTip(name: string): void {
  expandedTips.value[name] = !expandedTips.value[name];
}
function toggleSection(key: string): void {
  collapsedSections.value[key] = !collapsedSections.value[key];
}
function sectionOpen(key: string): boolean {
  return !collapsedSections.value[key];
}

function paramValue(prop: NodeProperty): unknown {
  const value = props.node.parameters?.[prop.name];
  if (value !== undefined) return value;
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
  try {
    emit("update-parameter", prop.name, raw === "" ? null : JSON.parse(raw));
  } catch {
    emit("update-parameter", prop.name, raw);
  }
}

function asJsonString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function credentialsForSlot(slotTypes: string[]): CredentialSummary[] {
  return props.credentials.filter((c) => slotTypes.includes(c.type));
}
function currentCredentialFor(slotName: string): string {
  return props.node.credentials?.[slotName] ?? "";
}

function applySuggestion(prop: NodeProperty, value: string): void {
  if (prop.type === "number") {
    emit("update-parameter", prop.name, Number(value));
  } else if (prop.type === "json") {
    onJsonInput(prop, value);
  } else {
    emit("update-parameter", prop.name, value);
  }
}

function isValueFilled(prop: NodeProperty): boolean {
  const v = paramValue(prop);
  if (v === null || v === undefined) return false;
  if (typeof v === "string" && v.trim() === "") return false;
  return true;
}

function categoryTone(): string {
  return props.nodeType?.category ?? "core";
}

// Derive first-letter badge for the node type.
const typeInitial = computed(() =>
  (props.nodeType?.display_name ?? props.node.type).slice(0, 2).toUpperCase(),
);

const credentialCount = computed(() => (props.nodeType?.credentials ?? []).length);
const paramCount = computed(() => (props.nodeType?.properties ?? []).length);
const filledCount = computed(() =>
  (props.nodeType?.properties ?? []).filter(isValueFilled).length,
);
</script>

<template>
  <div
    class="form"
    data-testid="node-form"
  >
    <!-- HEADER --------------------------------------------------------- -->
    <div class="node-card" :data-tone="categoryTone()">
      <div class="nc-badge" aria-hidden="true">{{ typeInitial }}</div>
      <div class="nc-body">
        <div class="nc-row">
          <input
            v-model="nameModel"
            class="nc-name"
            data-testid="node-name"
            placeholder="Node name"
          >
          <button
            class="nc-delete"
            data-testid="node-delete"
            aria-label="Delete node"
            title="Delete node"
            @click="emit('delete')"
          >
            <Trash2 :size="14" />
          </button>
        </div>
        <div class="nc-meta">
          <span class="nc-cat">{{ nodeType?.category ?? "unknown" }}</span>
          <span class="nc-dot" />
          <code class="nc-slug">{{ node.type }}</code>
        </div>
        <p
          v-if="nodeType?.description"
          class="nc-desc"
        >{{ nodeType.description }}</p>
        <div class="nc-stats">
          <span
            v-if="paramCount > 0"
            class="nc-stat"
            :data-ok="filledCount === paramCount"
          >
            <Sliders :size="11" /> {{ filledCount }}/{{ paramCount }} set
          </span>
          <span
            v-if="credentialCount > 0"
            class="nc-stat"
          >
            <KeyRound :size="11" /> {{ credentialCount }} credential{{ credentialCount > 1 ? "s" : "" }}
          </span>
        </div>
      </div>
    </div>

    <template v-if="nodeType">
      <!-- CREDENTIALS -------------------------------------------------- -->
      <section
        v-if="(nodeType.credentials || []).length > 0"
        class="group"
      >
        <button
          class="group-head"
          type="button"
          :aria-expanded="sectionOpen('cred')"
          @click="toggleSection('cred')"
        >
          <span class="gh-icon"><KeyRound :size="12" /></span>
          <span class="gh-title">Credentials</span>
          <span class="gh-count">{{ nodeType.credentials.length }}</span>
          <ChevronDown
            :size="14"
            class="gh-chevron"
            :class="{ open: sectionOpen('cred') }"
          />
        </button>
        <div
          v-if="sectionOpen('cred')"
          class="group-body"
        >
          <div
            v-for="slot in nodeType.credentials"
            :key="slot.name"
            class="field"
          >
            <label class="f-label">
              <Plug :size="11" class="f-icon" />
              {{ slot.name }}
              <span
                v-if="slot.required"
                class="required"
                title="Required"
              >*</span>
            </label>
            <div class="f-input-wrap">
              <select
                class="f-input"
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
                <option value="">— none —</option>
                <option
                  v-for="cred in credentialsForSlot(slot.credential_types)"
                  :key="cred.id"
                  :value="cred.id"
                >{{ cred.name }} ({{ cred.type }})</option>
              </select>
            </div>
            <p
              v-if="credentialsForSlot(slot.credential_types).length === 0"
              class="f-empty"
            >
              <AlertCircle :size="12" />
              No matching credential yet — create one from the Credentials tab.
              Accepts: {{ slot.credential_types.join(", ") }}
            </p>
          </div>
        </div>
      </section>

      <!-- PARAMETERS --------------------------------------------------- -->
      <section
        v-if="nodeType.properties.length > 0"
        class="group"
      >
        <button
          class="group-head"
          type="button"
          :aria-expanded="sectionOpen('params')"
          @click="toggleSection('params')"
        >
          <span class="gh-icon"><Sliders :size="12" /></span>
          <span class="gh-title">Parameters</span>
          <span class="gh-count">{{ nodeType.properties.length }}</span>
          <ChevronDown
            :size="14"
            class="gh-chevron"
            :class="{ open: sectionOpen('params') }"
          />
        </button>
        <div
          v-if="sectionOpen('params')"
          class="group-body"
        >
          <div
            v-for="prop in nodeType.properties"
            :key="prop.name"
            class="field"
            :data-filled="isValueFilled(prop)"
          >
            <label class="f-label">
              <span class="f-name">{{ prop.display_name }}</span>
              <span
                v-if="prop.required"
                class="required"
                title="Required"
              >*</span>
              <CheckCircle2
                v-if="isValueFilled(prop)"
                :size="12"
                class="f-filled-dot"
                aria-label="Filled"
              />
              <span class="f-spacer" />
              <button
                v-if="helpFor(prop).tip"
                class="f-help-btn"
                type="button"
                :title="expandedTips[prop.name] ? 'Hide tip' : 'Show tip'"
                @click="toggleTip(prop.name)"
              >
                <HelpCircle :size="13" />
              </button>
            </label>

            <!-- INPUT BY TYPE -->
            <div class="f-input-wrap">
              <template v-if="prop.type === 'boolean'">
                <label class="f-switch">
                  <input
                    type="checkbox"
                    :checked="Boolean(paramValue(prop))"
                    :data-testid="`node-param-${prop.name}`"
                    @change="onInput(prop, ($event.target as HTMLInputElement).checked)"
                  >
                  <span class="f-switch-track"><span class="f-switch-thumb" /></span>
                  <span class="f-switch-label">
                    {{ Boolean(paramValue(prop)) ? "Enabled" : "Disabled" }}
                  </span>
                </label>
              </template>
              <template v-else-if="prop.type === 'options'">
                <select
                  class="f-input"
                  :value="paramValue(prop) ?? ''"
                  :data-testid="`node-param-${prop.name}`"
                  @change="onInput(prop, ($event.target as HTMLSelectElement).value)"
                >
                  <option
                    v-if="!prop.required"
                    value=""
                  >— default —</option>
                  <option
                    v-for="opt in prop.options || []"
                    :key="opt.value"
                    :value="opt.value"
                    :title="opt.description ?? ''"
                  >{{ opt.label }}</option>
                </select>
              </template>
              <template v-else-if="prop.type === 'number'">
                <input
                  class="f-input"
                  type="number"
                  :value="paramValue(prop) ?? ''"
                  :placeholder="helpFor(prop).placeholder"
                  :data-testid="`node-param-${prop.name}`"
                  @input="onInput(prop, ($event.target as HTMLInputElement).value)"
                >
              </template>
              <template v-else-if="prop.type === 'json'">
                <textarea
                  class="f-input f-code"
                  :value="asJsonString(paramValue(prop))"
                  :placeholder="helpFor(prop).placeholder"
                  :data-testid="`node-param-${prop.name}`"
                  spellcheck="false"
                  rows="4"
                  @input="onJsonInput(prop, ($event.target as HTMLTextAreaElement).value)"
                />
              </template>
              <template v-else>
                <input
                  class="f-input"
                  :type="prop.type_options?.password ? 'password' : 'text'"
                  :value="paramValue(prop) ?? ''"
                  :placeholder="helpFor(prop).placeholder"
                  :data-testid="`node-param-${prop.name}`"
                  @input="onInput(prop, ($event.target as HTMLInputElement).value)"
                >
              </template>
            </div>

            <!-- INLINE EXAMPLE -->
            <p
              v-if="helpFor(prop).example && prop.type !== 'boolean'"
              class="f-example"
            >
              <Lightbulb :size="11" />
              <span class="f-example-label">e.g.</span>
              <code>{{ helpFor(prop).example }}</code>
            </p>

            <!-- SUGGESTION CHIPS -->
            <div
              v-if="helpFor(prop).suggestions.length > 0 && prop.type !== 'boolean'"
              class="f-chips"
            >
              <button
                v-for="chip in helpFor(prop).suggestions"
                :key="chip"
                type="button"
                class="f-chip"
                :data-testid="`node-param-${prop.name}-chip`"
                :title="`Insert: ${chip}`"
                @click="applySuggestion(prop, chip)"
              >
                <Wand2 :size="10" />
                <span>{{ chip }}</span>
              </button>
            </div>

            <!-- EXPANDED TIP -->
            <transition name="tip">
              <p
                v-if="expandedTips[prop.name] && helpFor(prop).tip"
                class="f-tip"
              >
                <Info :size="12" />
                <span>{{ helpFor(prop).tip }}</span>
              </p>
            </transition>
          </div>
        </div>
      </section>

      <!-- TIPS FOOTER -------------------------------------------------- -->
      <div class="tips-card">
        <Sparkles :size="12" />
        <div>
          <strong>Pro tip.</strong>
          Type <code v-pre>{{ $json.fieldName }}</code> in any text field to reference data from the previous node. Prefix a JSON string with <code v-pre>=</code> to evaluate it as an expression.
        </div>
      </div>
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
  padding: 16px 14px 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* ---------------- Node header card ---------------- */
.node-card {
  position: relative;
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 12px;
  padding: 12px 12px 12px 12px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.9), rgba(22, 25, 36, 0.9));
  border: 1px solid var(--wf-border, #262a36);
  overflow: hidden;
}
.node-card::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 14px;
  padding: 1px;
  background: linear-gradient(135deg, var(--cat-a, #5c8dff), transparent 55%, var(--cat-b, #8b5cff));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}
.node-card[data-tone="trigger"]     { --cat-a: #f0b455; --cat-b: #f76c6c; }
.node-card[data-tone="integration"] { --cat-a: #5c8dff; --cat-b: #8b5cff; }
.node-card[data-tone="ai"]          { --cat-a: #3dd28d; --cat-b: #5c8dff; }
.node-card[data-tone="core"]        { --cat-a: #8b5cff; --cat-b: #5c8dff; }

.nc-badge {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 0.04em;
  color: #0f1117;
  background: linear-gradient(135deg, var(--cat-a, #5c8dff), var(--cat-b, #8b5cff));
  box-shadow: 0 8px 20px -8px rgba(92, 141, 255, 0.55),
              inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}
.nc-body { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.nc-row { display: flex; align-items: center; gap: 8px; }
.nc-name {
  flex: 1;
  min-width: 0;
  background: rgba(15, 17, 23, 0.6);
  border: 1px solid var(--wf-border, #262a36);
  color: var(--wf-text, #e7eaf3);
  padding: 7px 10px;
  border-radius: 9px;
  font-size: 13.5px;
  font-weight: 600;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.nc-name:focus {
  outline: none;
  border-color: rgba(92, 141, 255, 0.6);
  box-shadow: 0 0 0 3px rgba(92, 141, 255, 0.18);
}
.nc-delete {
  display: inline-grid;
  place-items: center;
  width: 30px; height: 30px;
  border-radius: 8px;
  background: rgba(247, 108, 108, 0.08);
  border: 1px solid rgba(247, 108, 108, 0.3);
  color: #f76c6c;
  cursor: pointer;
  padding: 0;
  transition: background 0.15s ease, color 0.15s ease;
}
.nc-delete:hover { background: rgba(247, 108, 108, 0.18); color: #ff8a8a; }

.nc-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--wf-text-muted, #9aa3b2);
}
.nc-cat {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600;
  color: #b9c5ff;
}
.nc-dot { width: 3px; height: 3px; border-radius: 50%; background: var(--wf-text-muted, #9aa3b2); opacity: 0.6; }
.nc-slug { font-family: var(--wf-font-mono); font-size: 11px; color: var(--wf-text-muted, #9aa3b2); }
.nc-desc {
  margin: 2px 0 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--wf-text-muted, #9aa3b2);
}
.nc-stats {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.nc-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 3px 7px;
  border-radius: 999px;
  color: var(--wf-text-muted, #9aa3b2);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--wf-border, #262a36);
}
.nc-stat[data-ok="true"] {
  color: #3dd28d;
  border-color: rgba(61, 210, 141, 0.35);
  background: rgba(61, 210, 141, 0.08);
}

/* ---------------- Collapsible section ---------------- */
.group { display: flex; flex-direction: column; gap: 8px; }
.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--wf-border, #262a36);
  background: linear-gradient(135deg, rgba(92, 141, 255, 0.08), rgba(139, 92, 255, 0.05));
  color: var(--wf-text, #e7eaf3);
  cursor: pointer;
  font-family: inherit;
}
.group-head:hover { border-color: rgba(92, 141, 255, 0.4); }
.gh-icon {
  display: inline-grid;
  place-items: center;
  width: 22px; height: 22px;
  border-radius: 7px;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  color: #0f1117;
}
.gh-title { font-size: 12.5px; font-weight: 700; letter-spacing: 0.02em; }
.gh-count {
  font-size: 10.5px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(92, 141, 255, 0.18);
  color: #b9c5ff;
  border: 1px solid rgba(92, 141, 255, 0.3);
}
.gh-chevron {
  margin-left: auto;
  color: var(--wf-text-muted, #9aa3b2);
  transition: transform 0.2s ease;
}
.gh-chevron.open { transform: rotate(180deg); }

.group-body { display: flex; flex-direction: column; gap: 12px; padding: 4px 2px 2px 2px; }

/* ---------------- Field ---------------- */
.field { display: flex; flex-direction: column; gap: 6px; }
.field[data-filled="true"] .f-input {
  border-color: rgba(61, 210, 141, 0.3);
}
.f-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #d1d6e0;
}
.f-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.f-icon { color: var(--wf-text-muted, #9aa3b2); }
.f-spacer { flex: 1; }
.required { color: var(--wf-danger, #f76c6c); font-weight: 700; }
.f-filled-dot { color: #3dd28d; }
.f-help-btn {
  display: inline-grid;
  place-items: center;
  width: 22px; height: 22px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: var(--wf-text-muted, #9aa3b2);
  cursor: pointer;
  padding: 0;
  transition: background 0.15s ease, color 0.15s ease;
}
.f-help-btn:hover { background: rgba(255, 255, 255, 0.06); color: #b9c5ff; }

.f-input-wrap { position: relative; }
.f-input {
  width: 100%;
  background: rgba(15, 17, 23, 0.72);
  border: 1px solid var(--wf-border, #262a36);
  color: var(--wf-text, #e7eaf3);
  padding: 8px 10px;
  border-radius: 9px;
  font-size: 13px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
  font-family: inherit;
}
.f-input::placeholder { color: #6b7280; }
.f-input:hover { border-color: rgba(92, 141, 255, 0.35); }
.f-input:focus {
  outline: none;
  border-color: rgba(92, 141, 255, 0.6);
  background: rgba(15, 17, 23, 0.9);
  box-shadow: 0 0 0 3px rgba(92, 141, 255, 0.18);
}
.f-code {
  font-family: var(--wf-font-mono);
  font-size: 12px;
  line-height: 1.5;
  resize: vertical;
  min-height: 96px;
}

/* Switch */
.f-switch {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}
.f-switch input { appearance: none; width: 0; height: 0; position: absolute; opacity: 0; }
.f-switch-track {
  position: relative;
  width: 40px;
  height: 22px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid var(--wf-border, #262a36);
  transition: background 0.2s ease, border-color 0.2s ease;
}
.f-switch-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #e7eaf3;
  transition: transform 0.2s ease, background 0.2s ease;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
}
.f-switch input:checked ~ .f-switch-track {
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  border-color: transparent;
}
.f-switch input:checked ~ .f-switch-track .f-switch-thumb { transform: translateX(18px); background: #0f1117; }
.f-switch input:checked + .f-switch-track { /* fallback for older browsers */ }
.f-switch-label { font-size: 12px; color: var(--wf-text-muted, #9aa3b2); }

/* Example line */
.f-example {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 11px;
  color: var(--wf-text-muted, #9aa3b2);
}
.f-example > svg { color: #f0b455; }
.f-example-label {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 700;
  color: #f0b455;
  font-size: 9.5px;
}
.f-example code {
  font-family: var(--wf-font-mono);
  font-size: 11px;
  color: #d1d6e0;
  background: rgba(255, 255, 255, 0.04);
  padding: 2px 6px;
  border-radius: 6px;
  border: 1px solid var(--wf-border, #262a36);
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  white-space: nowrap;
}

/* Suggestion chips */
.f-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.f-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  font-size: 10.5px;
  font-family: var(--wf-font-mono);
  color: #b9c5ff;
  background: rgba(92, 141, 255, 0.08);
  border: 1px solid rgba(92, 141, 255, 0.25);
  padding: 3px 7px;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, transform 0.12s ease;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.f-chip:hover {
  background: rgba(92, 141, 255, 0.18);
  border-color: rgba(92, 141, 255, 0.5);
  color: #e7eaf3;
  transform: translateY(-1px);
}
.f-chip > span {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

/* Expanded tip */
.f-tip {
  display: flex;
  gap: 6px;
  margin: 0;
  padding: 8px 10px;
  font-size: 11.5px;
  line-height: 1.5;
  color: #d1d6e0;
  background: rgba(92, 141, 255, 0.06);
  border: 1px solid rgba(92, 141, 255, 0.2);
  border-radius: 8px;
}
.f-tip > svg { flex-shrink: 0; margin-top: 2px; color: #5c8dff; }

.tip-enter-active, .tip-leave-active { transition: opacity 0.2s ease, max-height 0.25s ease; }
.tip-enter-from, .tip-leave-to { opacity: 0; max-height: 0; }
.tip-enter-to, .tip-leave-from { opacity: 1; max-height: 120px; }

/* Credential empty state */
.f-empty {
  display: inline-flex;
  align-items: flex-start;
  gap: 6px;
  margin: 4px 0 0 0;
  padding: 7px 10px;
  font-size: 11px;
  line-height: 1.5;
  color: #f0b455;
  background: rgba(240, 180, 85, 0.06);
  border: 1px solid rgba(240, 180, 85, 0.25);
  border-radius: 8px;
}
.f-empty > svg { flex-shrink: 0; margin-top: 1px; }

/* Tips card */
.tips-card {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--wf-text-muted, #9aa3b2);
  background: linear-gradient(135deg, rgba(92, 141, 255, 0.06), rgba(139, 92, 255, 0.04));
  border: 1px solid rgba(92, 141, 255, 0.2);
}
.tips-card > svg { flex-shrink: 0; margin-top: 2px; color: #b9c5ff; }
.tips-card code {
  font-family: var(--wf-font-mono);
  font-size: 11px;
  color: #b9c5ff;
  background: rgba(92, 141, 255, 0.1);
  padding: 1px 4px;
  border-radius: 4px;
}

.meta {
  color: var(--wf-text-muted, #9aa3b2);
  font-family: var(--wf-font-mono);
  font-size: 11px;
  margin: 0;
}
</style>
