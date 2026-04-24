<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { extractErrorMessage } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useNodeTypesStore } from "@/stores/nodeTypes";

const auth = useAuthStore();
const nodeTypes = useNodeTypesStore();
const router = useRouter();
const route = useRoute();

const email = ref("");
const password = ref("");
const submitting = ref(false);
const errorMessage = ref<string | null>(null);

async function onSubmit(): Promise<void> {
  if (submitting.value) {
    return;
  }
  submitting.value = true;
  errorMessage.value = null;
  try {
    await auth.login(email.value.trim(), password.value);
    await nodeTypes.loadOnce();
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.push(redirect);
  } catch (err) {
    errorMessage.value = extractErrorMessage(err);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login">
    <div
      class="bg-blobs"
      aria-hidden="true"
    >
      <span class="blob blob-a" />
      <span class="blob blob-b" />
      <span class="blob blob-c" />
      <span class="grid" />
    </div>

    <form
      class="panel"
      @submit.prevent="onSubmit"
    >
      <div class="brand">
        <span
          class="brand-mark"
          aria-hidden="true"
        />
        <h1>Weftlyflow</h1>
      </div>
      <p class="subtitle">
        Sign in to your workspace
      </p>

      <label for="login-email">Email</label>
      <input
        id="login-email"
        v-model="email"
        data-testid="login-email"
        type="email"
        autocomplete="email"
        placeholder="you@company.com"
        required
      >
      <label for="login-password">Password</label>
      <input
        id="login-password"
        v-model="password"
        data-testid="login-password"
        type="password"
        autocomplete="current-password"
        placeholder="••••••••"
        required
      >

      <p
        v-if="errorMessage"
        class="error"
        data-testid="login-error"
      >
        {{ errorMessage }}
      </p>

      <button
        class="primary"
        data-testid="login-submit"
        type="submit"
        :disabled="submitting"
      >
        <span
          v-if="submitting"
          class="spinner"
          aria-hidden="true"
        />
        <span>{{ submitting ? "Signing in…" : "Sign in" }}</span>
      </button>

      <p class="hint">
        Self-hosted workflow automation · v1.0
      </p>
    </form>
  </div>
</template>

<style scoped>
.login {
  position: relative;
  display: grid;
  place-items: center;
  height: 100%;
  padding: 40px;
  overflow: hidden;
}

.bg-blobs {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}
.blob {
  position: absolute;
  width: 520px;
  height: 520px;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.55;
  animation: float 16s ease-in-out infinite;
}
.blob-a {
  top: -120px; left: -120px;
  background: radial-gradient(circle at 30% 30%, #5c8dff, transparent 60%);
}
.blob-b {
  bottom: -160px; right: -140px;
  background: radial-gradient(circle at 70% 70%, #8b5cff, transparent 60%);
  animation-delay: -5s;
}
.blob-c {
  top: 30%; left: 45%;
  width: 360px; height: 360px;
  background: radial-gradient(circle at 50% 50%, #3dd28d, transparent 65%);
  opacity: 0.28;
  animation-delay: -10s;
}
@keyframes float {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
  50%      { transform: translate3d(20px, -30px, 0) scale(1.06); }
}
.grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: radial-gradient(ellipse at center, black 20%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 20%, transparent 75%);
}

.panel {
  position: relative;
  z-index: 1;
  width: 400px;
  padding: 34px 32px 28px;
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.82), rgba(22, 25, 36, 0.82));
  border: 1px solid rgba(92, 141, 255, 0.22);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow:
    0 30px 80px -30px rgba(92, 141, 255, 0.45),
    0 1px 0 0 rgba(255, 255, 255, 0.06) inset;
}
.panel::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 16px;
  padding: 1px;
  background: linear-gradient(135deg, rgba(92, 141, 255, 0.45), transparent 40%, rgba(139, 92, 255, 0.4));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background:
    conic-gradient(from 210deg at 50% 50%,
      #5c8dff 0deg, #8b5cff 120deg, #3dd28d 240deg, #5c8dff 360deg);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset,
              0 8px 22px -6px rgba(92, 141, 255, 0.7);
  animation: brand-spin 12s linear infinite;
}
@keyframes brand-spin { to { transform: rotate(360deg); } }

.panel h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.01em;
  background: linear-gradient(90deg, #e7eaf3, #b9c5ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.subtitle {
  margin: 0 0 14px 0;
  color: var(--wf-text-muted);
  font-size: 13px;
}

.panel label {
  font-size: 12px;
  color: var(--wf-text-muted);
  margin-top: 4px;
}
.panel input {
  background: rgba(15, 17, 23, 0.6);
  border: 1px solid var(--wf-border);
  padding: 10px 12px;
  border-radius: 10px;
  color: var(--wf-text);
  font-size: 14px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}
.panel input:focus {
  outline: none;
  border-color: rgba(92, 141, 255, 0.6);
  background: rgba(15, 17, 23, 0.85);
  box-shadow: 0 0 0 4px rgba(92, 141, 255, 0.18);
}

.panel button.primary {
  margin-top: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 14px;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: #0f1117;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  cursor: pointer;
  box-shadow: 0 14px 32px -12px rgba(92, 141, 255, 0.55),
              0 0 0 1px rgba(255, 255, 255, 0.08) inset;
  transition: transform 0.12s ease, box-shadow 0.15s ease, filter 0.15s ease;
}
.panel button.primary:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.05);
  box-shadow: 0 18px 40px -12px rgba(92, 141, 255, 0.7);
}
.panel button.primary:disabled {
  cursor: progress;
  opacity: 0.8;
}

.spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(15, 17, 23, 0.3);
  border-top-color: #0f1117;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error {
  color: var(--wf-danger);
  font-size: 13px;
  margin: 6px 0 0 0;
  padding: 8px 10px;
  background: rgba(247, 108, 108, 0.1);
  border: 1px solid rgba(247, 108, 108, 0.28);
  border-radius: 8px;
}

.hint {
  margin: 14px 0 0 0;
  font-size: 11px;
  color: var(--wf-text-muted);
  text-align: center;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
</style>
