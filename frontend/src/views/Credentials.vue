<script setup lang="ts">
import { AlertCircle, CheckCircle2, KeyRound, Plus, ShieldCheck, Trash2 } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

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
const testingId = ref<string | null>(null);

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
  testingId.value = id;
  try {
    testResults.value = { ...testResults.value, [id]: await store.test(id) };
  } catch (err) {
    actionError.value = extractErrorMessage(err);
  } finally {
    testingId.value = null;
  }
}

// ----- Visuals: deterministic palette + initial per credential type ---------

const TYPE_PALETTE = [
  ["#5c8dff", "#8b5cff"],
  ["#3dd28d", "#5c8dff"],
  ["#f0b455", "#f76c6c"],
  ["#8b5cff", "#f76c6c"],
  ["#3dd28d", "#f0b455"],
  ["#55c8e6", "#5c8dff"],
  ["#f76cc6", "#8b5cff"],
] as const;

function paletteFor(slug: string): readonly [string, string] {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return TYPE_PALETTE[h % TYPE_PALETTE.length];
}

function typeInitial(slug: string): string {
  const entry = store.types.find((t) => t.slug === slug);
  const name = entry?.display_name ?? slug.replace(/^.*\./, "");
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function typeLabel(slug: string): string {
  return store.types.find((t) => t.slug === slug)?.display_name ?? slug;
}

const hasItems = computed(() => store.items.length > 0);
</script>

<template>
  <div class="credentials">
    <section class="cred-card">
      <header class="cred-head">
        <div class="cred-head-main">
          <span class="cred-logo">
            <ShieldCheck :size="16" />
          </span>
          <div class="cred-heading">
            <h2>Credentials</h2>
            <p class="cred-sub">
              Encrypted tokens and API keys stored in the vault.
              <span class="cred-count">{{ store.items.length }} stored</span>
              <span class="cred-count alt">{{ store.types.length }} types</span>
            </p>
          </div>
        </div>
        <button
          class="cred-cta"
          data-testid="new-credential"
          @click="openNew"
        >
          <Plus :size="14" />
          <span>New credential</span>
        </button>
      </header>

      <div
        v-if="actionError"
        class="cred-alert"
        role="alert"
      >
        <span class="cred-alert-icon">
          <AlertCircle :size="16" />
        </span>
        <div class="cred-alert-body">
          <span class="cred-alert-title">Something went wrong</span>
          <span class="cred-alert-msg">{{ actionError }}</span>
        </div>
        <button
          class="cred-alert-close"
          aria-label="Dismiss alert"
          @click="actionError = null"
        >
          ×
        </button>
      </div>

      <p
        v-if="store.loading"
        class="cred-muted"
      >
        Loading…
      </p>

      <div
        v-else-if="!hasItems"
        class="cred-empty"
      >
        <KeyRound :size="26" />
        <p class="cred-empty-title">
          No credentials yet
        </p>
        <p class="cred-empty-sub">
          Click <strong>New credential</strong> to add an OAuth token or API key.
        </p>
      </div>

      <div
        v-else
        class="cred-grid"
        data-testid="credentials-table"
      >
        <article
          v-for="row in store.items"
          :key="row.id"
          class="cred-row"
          :data-credential-id="row.id"
          :style="{
            '--cred-from': paletteFor(row.type)[0],
            '--cred-to': paletteFor(row.type)[1],
          }"
        >
          <span class="cred-icon">
            {{ typeInitial(row.type) }}
          </span>
          <div class="cred-body">
            <span class="cred-name">{{ row.name }}</span>
            <span class="cred-type">{{ typeLabel(row.type) }}</span>
            <span class="cred-slug">{{ row.type }}</span>
          </div>
          <div class="cred-actions">
            <span
              v-if="testResults[row.id]"
              class="wf-badge"
              :class="testResults[row.id].ok ? 'success' : 'error'"
            >
              <CheckCircle2
                v-if="testResults[row.id].ok"
                :size="11"
              />
              <AlertCircle
                v-else
                :size="11"
              />
              {{ testResults[row.id].ok ? "ok" : testResults[row.id].message }}
            </span>
            <button
              class="cred-btn ghost"
              :disabled="testingId === row.id"
              @click="onTest(row.id)"
            >
              {{ testingId === row.id ? "Testing…" : "Test" }}
            </button>
            <button
              class="cred-btn danger"
              :title="`Delete ${row.name}`"
              @click="onDelete(row.id, row.name)"
            >
              <Trash2 :size="13" />
            </button>
          </div>
        </article>
      </div>
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
  max-width: 1060px;
  margin: 0 auto;
  padding: 28px 24px 56px;
}

/* ---------- card shell ---------- */
.cred-card {
  position: relative;
  border-radius: 16px;
  padding: 20px 22px 22px;
  background:
    radial-gradient(600px 200px at 0% 0%, rgba(92, 141, 255, 0.12), transparent 65%),
    radial-gradient(500px 220px at 100% 100%, rgba(139, 92, 255, 0.1), transparent 60%),
    linear-gradient(180deg, rgba(28, 31, 44, 0.8), rgba(22, 25, 36, 0.8));
  border: 1px solid var(--wf-border, rgba(255, 255, 255, 0.08));
  overflow: hidden;
}
.cred-card::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 16px;
  padding: 1px;
  background: linear-gradient(135deg, rgba(92, 141, 255, 0.5), transparent 55%, rgba(139, 92, 255, 0.4));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
  opacity: 0.6;
}

/* ---------- header ---------- */
.cred-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  position: relative;
}
.cred-head-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.cred-logo {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  color: #0f1117;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  box-shadow: 0 12px 28px -14px rgba(92, 141, 255, 0.7),
              inset 0 0 0 1px rgba(255, 255, 255, 0.18);
  flex: 0 0 auto;
}
.cred-heading { min-width: 0; }
.cred-heading h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  background: linear-gradient(100deg, #ffffff, #b9c5ff 60%, #8b5cff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.cred-sub {
  margin: 3px 0 0 0;
  font-size: 12.5px;
  color: var(--wf-text-muted, #8c93a1);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cred-count {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 600;
  color: #b9c5ff;
  background: rgba(92, 141, 255, 0.12);
  border: 1px solid rgba(92, 141, 255, 0.28);
}
.cred-count.alt {
  color: #bff2d9;
  background: rgba(61, 210, 141, 0.12);
  border-color: rgba(61, 210, 141, 0.3);
}
.cred-cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 14px;
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: #0f1117;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: transform 0.12s ease, filter 0.15s ease;
  box-shadow: 0 12px 28px -12px rgba(92, 141, 255, 0.65),
              inset 0 0 0 1px rgba(255, 255, 255, 0.1);
  flex: 0 0 auto;
}
.cred-cta:hover { transform: translateY(-1px); filter: brightness(1.06); }

/* ---------- alert ---------- */
.cred-alert {
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
  animation: cred-alert-in 0.2s ease-out;
}
.cred-alert::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(247, 108, 108, 0.18), transparent 35%);
  pointer-events: none;
}
@keyframes cred-alert-in {
  from { opacity: 0; transform: translateY(-3px); }
  to   { opacity: 1; transform: translateY(0); }
}
.cred-alert-icon {
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
.cred-alert-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
  position: relative;
  z-index: 1;
}
.cred-alert-title {
  font-size: 12.5px;
  font-weight: 700;
  color: #ffd4d4;
  letter-spacing: 0.01em;
}
.cred-alert-msg {
  font-size: 12.5px;
  color: #f0b0b0;
  line-height: 1.5;
  word-break: break-word;
}
.cred-alert-close {
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
.cred-alert-close:hover { color: #ffffff; }

/* ---------- empty state ---------- */
.cred-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 40px 20px;
  text-align: center;
  color: var(--wf-text-muted, #8c93a1);
}
.cred-empty :deep(svg) { opacity: 0.6; margin-bottom: 6px; }
.cred-empty-title { margin: 0; font-size: 14px; color: var(--wf-text, #ffffff); font-weight: 600; }
.cred-empty-sub   { margin: 2px 0 0; font-size: 12.5px; }
.cred-muted { margin: 14px 0 0; color: var(--wf-text-muted, #8c93a1); }

/* ---------- grid of credential rows ---------- */
.cred-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 10px;
  margin-top: 6px;
}
.cred-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.85), rgba(18, 20, 28, 0.9));
  border: 1px solid var(--wf-border, rgba(255, 255, 255, 0.06));
  overflow: hidden;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.2s ease;
}
.cred-row::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 12px;
  padding: 1px;
  background: linear-gradient(135deg, var(--cred-from, #5c8dff), transparent 55%, var(--cred-to, #8b5cff));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
  opacity: 0.35;
  transition: opacity 0.2s ease;
}
.cred-row:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 30px -18px var(--cred-from, rgba(92, 141, 255, 0.5));
}
.cred-row:hover::before { opacity: 0.9; }

.cred-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  color: #0f1117;
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.02em;
  background: linear-gradient(135deg, var(--cred-from, #5c8dff), var(--cred-to, #8b5cff));
  box-shadow: 0 10px 22px -10px var(--cred-from, rgba(92, 141, 255, 0.6)),
              inset 0 0 0 1px rgba(255, 255, 255, 0.2);
  flex: 0 0 auto;
}
.cred-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.cred-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--wf-text, #ffffff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cred-type {
  font-size: 11.5px;
  color: var(--wf-text-muted, #c4cad4);
}
.cred-slug {
  font-size: 10.5px;
  font-family: var(--wf-font-mono, ui-monospace, Menlo, monospace);
  color: var(--wf-text-muted, #8c93a1);
  opacity: 0.75;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cred-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.cred-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  font-size: 11.5px;
  font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.cred-btn.ghost {
  color: var(--wf-text-muted, #c4cad4);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--wf-border, rgba(255, 255, 255, 0.08));
}
.cred-btn.ghost:hover:not(:disabled) {
  color: #ffffff;
  background: rgba(92, 141, 255, 0.14);
  border-color: rgba(92, 141, 255, 0.4);
}
.cred-btn.ghost:disabled { opacity: 0.6; cursor: progress; }
.cred-btn.danger {
  color: #f0b0b0;
  background: transparent;
  border: 1px solid transparent;
}
.cred-btn.danger:hover {
  color: #ffffff;
  background: rgba(247, 108, 108, 0.15);
  border-color: rgba(247, 108, 108, 0.4);
}

/* Preserve existing .wf-badge test hook — upgrade visuals only */
.wf-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  letter-spacing: 0.02em;
}
.wf-badge.success {
  color: #bff2d9;
  background: rgba(61, 210, 141, 0.14);
  border: 1px solid rgba(61, 210, 141, 0.38);
}
.wf-badge.error {
  color: #ffd4d4;
  background: rgba(247, 108, 108, 0.14);
  border: 1px solid rgba(247, 108, 108, 0.38);
}
</style>
