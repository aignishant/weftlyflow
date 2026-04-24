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
    <form
      class="panel"
      @submit.prevent="onSubmit"
    >
      <h1>Weftlyflow</h1>
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
        required
      >
      <label for="login-password">Password</label>
      <input
        id="login-password"
        v-model="password"
        data-testid="login-password"
        type="password"
        autocomplete="current-password"
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
        {{ submitting ? "Signing in…" : "Sign in" }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  height: 100%;
  padding: 40px;
}
.panel {
  width: 360px;
  padding: 32px;
  background: var(--wf-bg-elevated);
  border: 1px solid var(--wf-border);
  border-radius: var(--wf-radius);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.panel h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.01em;
}
.subtitle {
  margin: 0 0 12px 0;
  color: var(--wf-text-muted);
}
.panel button {
  margin-top: 12px;
}
.error {
  color: var(--wf-danger);
  font-size: 13px;
  margin: 0;
}
</style>
