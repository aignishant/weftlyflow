<script setup lang="ts">
import { HelpCircle, Key, LogOut, Play, Workflow } from "lucide-vue-next";
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { CREDENTIALS_TOUR, EDITOR_TOUR, EXECUTIONS_TOUR, HOME_TOUR, resetTour, startTour } from "@/lib/tour";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const helpOpen = ref(false);

async function onLogout(): Promise<void> {
  await auth.logout();
  await router.push({ name: "login" });
}

function replayDashboardTour(): void {
  resetTour(HOME_TOUR.id);
  helpOpen.value = false;
  if (route.name === "home") {
    startTour(HOME_TOUR, { force: true });
  } else {
    router.push({ name: "home" }).then(() =>
      setTimeout(() => startTour(HOME_TOUR, { force: true }), 300),
    );
  }
}

function replayEditorTour(): void {
  helpOpen.value = false;
  resetTour(EDITOR_TOUR.id);
  if (route.name === "editor") {
    startTour(EDITOR_TOUR, { force: true });
  }
}

function replayCredentialsTour(): void {
  helpOpen.value = false;
  resetTour(CREDENTIALS_TOUR.id);
  if (route.name === "credentials") {
    startTour(CREDENTIALS_TOUR, { force: true });
  } else {
    router.push({ name: "credentials" }).then(() =>
      setTimeout(() => startTour(CREDENTIALS_TOUR, { force: true }), 300),
    );
  }
}

function replayExecutionsTour(): void {
  helpOpen.value = false;
  resetTour(EXECUTIONS_TOUR.id);
  if (route.name === "executions") {
    startTour(EXECUTIONS_TOUR, { force: true });
  } else {
    router.push({ name: "executions" }).then(() =>
      setTimeout(() => startTour(EXECUTIONS_TOUR, { force: true }), 300),
    );
  }
}

function resetAllTours(): void {
  resetTour("all");
  helpOpen.value = false;
}
</script>

<template>
  <header class="topbar">
    <RouterLink
      :to="{ name: 'home' }"
      class="brand"
    >
      <span class="brand-mark" aria-hidden="true" />
      <span class="brand-text">Weftlyflow</span>
    </RouterLink>

    <nav class="nav">
      <RouterLink :to="{ name: 'home' }" class="nav-link">
        <Workflow :size="16" />
        <span>Workflows</span>
      </RouterLink>
      <RouterLink :to="{ name: 'executions' }" class="nav-link">
        <Play :size="16" />
        <span>Executions</span>
      </RouterLink>
      <RouterLink :to="{ name: 'credentials' }" class="nav-link">
        <Key :size="16" />
        <span>Credentials</span>
      </RouterLink>
    </nav>

    <div class="spacer" />

    <div v-if="auth.email" class="user">
      <span class="avatar" :title="auth.email">
        {{ auth.email.slice(0, 1).toUpperCase() }}
      </span>
      <span class="email">{{ auth.email }}</span>
    </div>
    <div class="help-wrap">
      <button
        class="help"
        data-testid="help-menu"
        aria-label="Help & tours"
        :aria-expanded="helpOpen"
        @click="helpOpen = !helpOpen"
      >
        <HelpCircle :size="14" />
        <span>Help</span>
      </button>
      <div
        v-if="helpOpen"
        class="help-menu"
        role="menu"
        @click.self="helpOpen = false"
      >
        <button class="hm-item" role="menuitem" @click="replayDashboardTour">
          <span class="hm-label">Replay dashboard tour</span>
          <span class="hm-hint">Walk through workflows, stats, integrations</span>
        </button>
        <button
          class="hm-item"
          role="menuitem"
          :disabled="route.name !== 'editor'"
          :title="route.name !== 'editor' ? 'Open a workflow first' : ''"
          @click="replayEditorTour"
        >
          <span class="hm-label">Replay editor tour</span>
          <span class="hm-hint">Palette · canvas · inspector · examples · save</span>
        </button>
        <button class="hm-item" role="menuitem" @click="replayCredentialsTour">
          <span class="hm-label">Replay credentials tour</span>
          <span class="hm-hint">Vault · encrypted storage · test button</span>
        </button>
        <button class="hm-item" role="menuitem" @click="replayExecutionsTour">
          <span class="hm-label">Replay executions tour</span>
          <span class="hm-hint">Run history · status · drill-down</span>
        </button>
        <div class="hm-sep" />
        <button class="hm-item" role="menuitem" @click="resetAllTours">
          <span class="hm-label">Reset all tours</span>
          <span class="hm-hint">They'll auto-play again on next visit</span>
        </button>
      </div>
    </div>
    <button
      class="logout"
      data-testid="logout"
      @click="onLogout"
    >
      <LogOut :size="14" />
      <span>Logout</span>
    </button>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 10px 20px;
  background:
    linear-gradient(180deg, rgba(22, 25, 36, 0.92), rgba(22, 25, 36, 0.78));
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(92, 141, 255, 0.14);
  box-shadow: 0 1px 0 0 rgba(255, 255, 255, 0.03) inset,
              0 8px 24px -18px rgba(92, 141, 255, 0.35);
  flex: 0 0 auto;
  position: relative;
  z-index: 10;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--wf-text);
  text-decoration: none;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.brand-mark {
  width: 22px;
  height: 22px;
  border-radius: 7px;
  background:
    conic-gradient(from 210deg at 50% 50%,
      #5c8dff 0deg, #8b5cff 120deg, #3dd28d 240deg, #5c8dff 360deg);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset,
              0 4px 14px -4px rgba(92, 141, 255, 0.6);
  animation: brand-spin 12s linear infinite;
}
.brand-text {
  background: linear-gradient(90deg, #e7eaf3, #b9c5ff 45%, #9aa3b2);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-size: 15px;
}
@keyframes brand-spin {
  to { transform: rotate(360deg); }
}

.nav {
  display: flex;
  gap: 4px;
  margin-left: 8px;
}
.nav-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--wf-text-muted);
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}
.nav-link:hover {
  color: var(--wf-text);
  background: rgba(255, 255, 255, 0.04);
}
.nav-link.router-link-active,
.nav-link.router-link-exact-active {
  color: var(--wf-text);
  background: linear-gradient(135deg, rgba(92, 141, 255, 0.22), rgba(139, 92, 255, 0.16));
  box-shadow: inset 0 0 0 1px rgba(92, 141, 255, 0.28),
              0 6px 18px -10px rgba(92, 141, 255, 0.55);
}

.spacer { flex: 1; }

.user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.avatar {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  color: #0f1117;
  font-weight: 700;
  font-size: 12px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.06);
}
.email {
  color: var(--wf-text-muted);
  font-size: 12px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.help-wrap { position: relative; }
.help {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  border-radius: 8px;
  background: rgba(92, 141, 255, 0.08);
  border: 1px solid rgba(92, 141, 255, 0.25);
  color: #b9c5ff;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}
.help:hover {
  color: #e7eaf3;
  background: rgba(92, 141, 255, 0.16);
  border-color: rgba(92, 141, 255, 0.45);
}
.help-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  width: 260px;
  padding: 6px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(28, 31, 44, 0.96), rgba(22, 25, 36, 0.96));
  border: 1px solid rgba(92, 141, 255, 0.3);
  box-shadow: 0 24px 48px -18px rgba(0, 0, 0, 0.6),
              0 0 0 1px rgba(255, 255, 255, 0.03) inset;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.hm-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 8px;
  background: transparent;
  border: none;
  color: var(--wf-text);
  cursor: pointer;
  text-align: left;
  transition: background 0.12s ease;
}
.hm-item:hover:not(:disabled) { background: rgba(92, 141, 255, 0.12); }
.hm-item:disabled { opacity: 0.5; cursor: not-allowed; }
.hm-label { font-size: 12.5px; font-weight: 600; letter-spacing: 0.01em; }
.hm-hint { font-size: 10.5px; color: var(--wf-text-muted); }
.hm-sep { height: 1px; margin: 4px 6px; background: var(--wf-border); }

.logout {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--wf-border);
  color: var(--wf-text-muted);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}
.logout:hover {
  color: var(--wf-text);
  background: rgba(247, 108, 108, 0.12);
  border-color: rgba(247, 108, 108, 0.4);
}
</style>
