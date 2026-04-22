// Auth store — holds the current bearer token + identity. Persists to
// localStorage via the api client helpers so a reload resumes the session
// until the server rejects the token.

import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { auth as authApi } from "@/api/endpoints";
import {
  getStoredProject,
  getStoredToken,
  setStoredProject,
  setStoredToken,
} from "@/api/client";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(null);
  const email = ref<string | null>(null);
  const userId = ref<string | null>(null);
  const projectId = ref<string | null>(null);

  const isAuthenticated = computed(() => token.value !== null);

  function hydrate(): void {
    token.value = getStoredToken();
    projectId.value = getStoredProject();
  }

  async function login(emailInput: string, password: string): Promise<void> {
    const response = await authApi.login(emailInput, password);
    token.value = response.access_token;
    setStoredToken(response.access_token);
    // Login returns tokens only — fetch the identity separately so we know
    // the default project to scope every subsequent request against.
    const me = await authApi.me();
    email.value = me.email;
    userId.value = me.id;
    projectId.value = me.default_project_id;
    setStoredProject(me.default_project_id);
  }

  async function logout(): Promise<void> {
    await authApi.logout();
    clear();
  }

  function clear(): void {
    token.value = null;
    email.value = null;
    userId.value = null;
    projectId.value = null;
    setStoredToken(null);
    setStoredProject(null);
  }

  return {
    token,
    email,
    userId,
    projectId,
    isAuthenticated,
    hydrate,
    login,
    logout,
    clear,
  };
});
