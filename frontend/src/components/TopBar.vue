<script setup lang="ts">
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

async function onLogout(): Promise<void> {
  await auth.logout();
  await router.push({ name: "login" });
}
</script>

<template>
  <header class="topbar">
    <RouterLink :to="{ name: 'home' }" class="brand">Weftlyflow</RouterLink>
    <nav class="nav">
      <RouterLink :to="{ name: 'home' }">Workflows</RouterLink>
      <RouterLink :to="{ name: 'executions' }">Executions</RouterLink>
      <RouterLink :to="{ name: 'credentials' }">Credentials</RouterLink>
    </nav>
    <div class="spacer" />
    <span class="email" v-if="auth.email">{{ auth.email }}</span>
    <button class="logout" data-testid="logout" @click="onLogout">Logout</button>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  background: var(--wf-bg-elevated);
  border-bottom: 1px solid var(--wf-border);
  flex: 0 0 auto;
}
.brand {
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--wf-text);
}
.nav {
  display: flex;
  gap: 12px;
  margin-left: 12px;
}
.nav a {
  color: var(--wf-text-muted);
  padding: 4px 8px;
  border-radius: var(--wf-radius);
}
.nav a.router-link-active,
.nav a.router-link-exact-active {
  color: var(--wf-text);
  background: rgba(92, 141, 255, 0.12);
}
.spacer {
  flex: 1;
}
.email {
  color: var(--wf-text-muted);
  font-size: 12px;
}
.logout {
  padding: 4px 10px;
}
</style>
