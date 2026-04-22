// Executions store — list + active-detail caching for the Executions view.

import { defineStore } from "pinia";
import { ref } from "vue";

import { executions as execApi } from "@/api/endpoints";
import type { ExecutionDetail, ExecutionSummary } from "@/types/api";

export const useExecutionsStore = defineStore("executions", () => {
  const items = ref<ExecutionSummary[]>([]);
  const current = ref<ExecutionDetail | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchList(workflowId?: string): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      items.value = await execApi.list(workflowId);
    } catch (err) {
      error.value = (err as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function fetchOne(id: string): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      current.value = await execApi.get(id);
    } catch (err) {
      error.value = (err as Error).message;
    } finally {
      loading.value = false;
    }
  }

  function clearCurrent(): void {
    current.value = null;
  }

  return { items, current, loading, error, fetchList, fetchOne, clearCurrent };
});
