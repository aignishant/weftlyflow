// Node-type catalog store — loaded once on login and cached until logout.
// The editor's palette + parameter-form generator read from here.

import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { nodeTypes as nodeTypesApi } from "@/api/endpoints";
import type { NodeType } from "@/types/api";

export const useNodeTypesStore = defineStore("nodeTypes", () => {
  const items = ref<NodeType[]>([]);
  const loaded = ref(false);
  const loading = ref(false);

  async function loadOnce(): Promise<void> {
    if (loaded.value || loading.value) {
      return;
    }
    loading.value = true;
    try {
      items.value = await nodeTypesApi.list();
      loaded.value = true;
    } finally {
      loading.value = false;
    }
  }

  function clear(): void {
    items.value = [];
    loaded.value = false;
  }

  const bySlug = computed(() => {
    const out = new Map<string, NodeType>();
    for (const entry of items.value) {
      out.set(entry.type, entry);
    }
    return out;
  });

  function lookup(slug: string): NodeType | undefined {
    return bySlug.value.get(slug);
  }

  return { items, loaded, loading, loadOnce, clear, lookup, bySlug };
});
