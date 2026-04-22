// Workflow list store — holds the list index for the Home view. The editor
// fetches individual workflows ad-hoc so their in-progress edits don't leak
// across views.

import { defineStore } from "pinia";
import { ref } from "vue";

import { workflows as workflowsApi } from "@/api/endpoints";
import type { Workflow, WorkflowCreate, WorkflowUpdate } from "@/types/api";

export const useWorkflowsStore = defineStore("workflows", () => {
  const items = ref<Workflow[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchAll(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      items.value = await workflowsApi.list();
    } catch (err) {
      error.value = (err as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function create(body: WorkflowCreate): Promise<Workflow> {
    const created = await workflowsApi.create(body);
    items.value = [created, ...items.value];
    return created;
  }

  async function update(id: string, body: WorkflowUpdate): Promise<Workflow> {
    const updated = await workflowsApi.update(id, body);
    items.value = items.value.map((w) => (w.id === id ? updated : w));
    return updated;
  }

  async function remove(id: string): Promise<void> {
    await workflowsApi.remove(id);
    items.value = items.value.filter((w) => w.id !== id);
  }

  async function setActive(id: string, active: boolean): Promise<Workflow> {
    const updated = active
      ? await workflowsApi.activate(id)
      : await workflowsApi.deactivate(id);
    items.value = items.value.map((w) => (w.id === id ? updated : w));
    return updated;
  }

  return { items, loading, error, fetchAll, create, update, remove, setActive };
});
