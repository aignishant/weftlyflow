<script setup lang="ts">
import { RouterView } from "vue-router";

import TopBar from "@/components/TopBar.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
auth.hydrate();
</script>

<template>
  <div class="weftlyflow-app">
    <TopBar v-if="auth.isAuthenticated" />
    <main class="weftlyflow-main">
      <RouterView />
    </main>
  </div>
</template>

<style>
.weftlyflow-app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.weftlyflow-main {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--wf-bg);
}
</style>
