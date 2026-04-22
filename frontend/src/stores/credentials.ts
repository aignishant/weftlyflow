// Credentials store — list + type catalog for the Credentials view and for
// the Editor's credential picker.

import { defineStore } from "pinia";
import { ref } from "vue";

import {
  credentialTypes as credentialTypesApi,
  credentials as credApi,
} from "@/api/endpoints";
import type {
  CredentialCreate,
  CredentialSummary,
  CredentialTestResult,
  CredentialTypeEntry,
  CredentialUpdate,
} from "@/types/api";

export const useCredentialsStore = defineStore("credentials", () => {
  const items = ref<CredentialSummary[]>([]);
  const types = ref<CredentialTypeEntry[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchAll(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const [creds, typeCatalog] = await Promise.all([
        credApi.list(),
        credentialTypesApi.list(),
      ]);
      items.value = creds;
      types.value = typeCatalog;
    } catch (err) {
      error.value = (err as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function create(body: CredentialCreate): Promise<CredentialSummary> {
    const created = await credApi.create(body);
    items.value = [created, ...items.value];
    return created;
  }

  async function update(
    id: string,
    body: CredentialUpdate,
  ): Promise<CredentialSummary> {
    const updated = await credApi.update(id, body);
    items.value = items.value.map((c) => (c.id === id ? updated : c));
    return updated;
  }

  async function remove(id: string): Promise<void> {
    await credApi.remove(id);
    items.value = items.value.filter((c) => c.id !== id);
  }

  async function test(id: string): Promise<CredentialTestResult> {
    return credApi.test(id);
  }

  return {
    items,
    types,
    loading,
    error,
    fetchAll,
    create,
    update,
    remove,
    test,
  };
});
