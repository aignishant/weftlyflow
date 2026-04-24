<script setup lang="ts">
// Collapsible list of node types grouped by category. Clicking an entry
// emits `select` so the parent adds a fresh node to the canvas.

import { computed, ref } from "vue";

import type { NodeType } from "@/types/api";

const props = defineProps<{
  types: NodeType[];
}>();

const emit = defineEmits<{
  (event: "select", nodeType: NodeType): void;
}>();

const filter = ref("");

const grouped = computed(() => {
  const filtered = props.types.filter((t) =>
    t.display_name.toLowerCase().includes(filter.value.toLowerCase()) ||
    t.type.toLowerCase().includes(filter.value.toLowerCase()),
  );
  const buckets = new Map<string, NodeType[]>();
  for (const entry of filtered) {
    const key = entry.category || "core";
    if (!buckets.has(key)) {
      buckets.set(key, []);
    }
    buckets.get(key)!.push(entry);
  }
  return Array.from(buckets.entries()).sort((a, b) => a[0].localeCompare(b[0]));
});
</script>

<template>
  <aside
    class="palette"
    data-testid="node-palette"
  >
    <header>
      <input
        v-model="filter"
        placeholder="Search nodes…"
        data-testid="palette-search"
      >
    </header>
    <section
      v-for="[category, entries] in grouped"
      :key="category"
      class="group"
    >
      <h3>{{ category }}</h3>
      <ul>
        <li
          v-for="entry in entries"
          :key="entry.type"
          :data-testid="`palette-add-${entry.type}`"
          @click="emit('select', entry)"
        >
          <span class="name">{{ entry.display_name }}</span>
          <span class="slug">{{ entry.type }}</span>
        </li>
      </ul>
    </section>
  </aside>
</template>

<style scoped>
.palette {
  width: 260px;
  min-width: 260px;
  background: var(--wf-bg-elevated);
  border-right: 1px solid var(--wf-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.palette header {
  padding: 12px;
  border-bottom: 1px solid var(--wf-border);
}
.group {
  padding: 8px 0;
  overflow-y: auto;
}
.group h3 {
  margin: 0;
  padding: 6px 12px;
  font-size: 11px;
  color: var(--wf-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.group ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.group li {
  padding: 8px 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.group li:hover {
  background: rgba(92, 141, 255, 0.1);
}
.name {
  font-weight: 500;
}
.slug {
  color: var(--wf-text-muted);
  font-family: var(--wf-font-mono);
  font-size: 11px;
}
</style>
