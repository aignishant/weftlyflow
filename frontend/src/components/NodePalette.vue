<script setup lang="ts">
// Collapsible list of node types grouped by category. Clicking an entry
// emits `select` so the parent adds a fresh node to the canvas.
//
// Keyboard support:
//   ↓ / ↑   move highlight among the flat filtered list (skips collapsed groups)
//   Enter   add the highlighted node
//   Esc     clear the search filter
//   /       focus the search input (scoped — palette only reacts when focused)

import { ChevronRight, Search } from "lucide-vue-next";
import { computed, ref, nextTick } from "vue";

import Input from "@/components/ui/Input.vue";
import { iconForNode } from "@/lib/node-icons";
import { cn } from "@/lib/utils";
import type { NodeType } from "@/types/api";

const props = defineProps<{
  types: NodeType[];
}>();

const emit = defineEmits<{
  (event: "select", nodeType: NodeType): void;
}>();

const filter = ref("");
const collapsed = ref<Record<string, boolean>>({});
const highlightIndex = ref(0);
const searchInput = ref<InstanceType<typeof Input> | null>(null);

const grouped = computed<Array<[string, NodeType[]]>>(() => {
  const needle = filter.value.trim().toLowerCase();
  const filtered = needle
    ? props.types.filter(
        (t) =>
          t.display_name.toLowerCase().includes(needle) ||
          t.type.toLowerCase().includes(needle),
      )
    : props.types;
  const buckets = new Map<string, NodeType[]>();
  for (const entry of filtered) {
    const key = entry.category || "core";
    if (!buckets.has(key)) {
      buckets.set(key, []);
    }
    buckets.get(key)!.push(entry);
  }
  // Canonical category ordering, with anything unexpected alpha-sorted at the end.
  const CATEGORY_ORDER = ["trigger", "core", "integration", "ai"];
  return Array.from(buckets.entries()).sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a[0]);
    const bi = CATEGORY_ORDER.indexOf(b[0]);
    if (ai === -1 && bi === -1) return a[0].localeCompare(b[0]);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
});

// Flat view of what the user can arrow through (respects collapsed groups).
const visibleEntries = computed<NodeType[]>(() => {
  const out: NodeType[] = [];
  for (const [cat, entries] of grouped.value) {
    if (collapsed.value[cat]) continue;
    out.push(...entries);
  }
  return out;
});

function toggleCategory(cat: string): void {
  collapsed.value = { ...collapsed.value, [cat]: !collapsed.value[cat] };
}

function onSearchKey(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    highlightIndex.value = Math.min(highlightIndex.value + 1, visibleEntries.value.length - 1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    highlightIndex.value = Math.max(highlightIndex.value - 1, 0);
  } else if (event.key === "Enter") {
    const target = visibleEntries.value[highlightIndex.value];
    if (target) {
      event.preventDefault();
      emit("select", target);
    }
  } else if (event.key === "Escape") {
    if (filter.value) {
      event.preventDefault();
      filter.value = "";
    }
  }
}

// Public: let parent call palette.focusSearch() (exposed via defineExpose).
async function focusSearch(): Promise<void> {
  await nextTick();
  const el = document.querySelector<HTMLInputElement>(
    '[data-testid="palette-search"] input',
  );
  el?.focus();
  el?.select();
}

defineExpose({ focusSearch });
</script>

<template>
  <aside
    class="flex flex-col w-[260px] shrink-0 bg-[var(--color-surface)] border-r border-[var(--color-border-subtle)] overflow-hidden"
    data-testid="node-palette"
  >
    <header class="p-3 border-b border-[var(--color-border-subtle)]">
      <div data-testid="palette-search">
        <Input
          ref="searchInput"
          v-model="filter"
          placeholder="Search nodes…"
          size="sm"
          @keydown="onSearchKey"
        >
          <template #leading>
            <Search class="h-3.5 w-3.5" />
          </template>
        </Input>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto py-2">
      <section
        v-for="[category, entries] in grouped"
        :key="category"
        class="mb-1"
      >
        <button
          type="button"
          class="w-full flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-foreground-subtle)] hover:text-[var(--color-foreground-muted)] transition-colors"
          @click="toggleCategory(category)"
        >
          <ChevronRight
            :class="cn(
              'h-3 w-3 transition-transform',
              !collapsed[category] && 'rotate-90',
            )"
          />
          <span>{{ category }}</span>
          <span class="ml-auto text-[10px] font-normal normal-case tracking-normal text-[var(--color-foreground-subtle)]">
            {{ entries.length }}
          </span>
        </button>

        <ul
          v-show="!collapsed[category]"
          class="list-none p-0 m-0"
        >
          <li
            v-for="entry in entries"
            :key="entry.type"
            :data-testid="`palette-add-${entry.type}`"
            :class="cn(
              'group flex items-center gap-2.5 px-3 py-2 cursor-pointer transition-colors',
              'hover:bg-[color-mix(in_srgb,var(--color-accent)_12%,transparent)]',
              visibleEntries[highlightIndex]?.type === entry.type && 'bg-[color-mix(in_srgb,var(--color-accent)_12%,transparent)]',
            )"
            @click="emit('select', entry)"
          >
            <div
              class="flex items-center justify-center h-7 w-7 rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] border border-[var(--color-border-subtle)] text-[var(--color-foreground-muted)] group-hover:text-[var(--color-accent)] group-hover:border-[var(--color-accent)] transition-colors shrink-0"
            >
              <component
                :is="iconForNode(entry.type, entry.category)"
                class="h-3.5 w-3.5"
              />
            </div>
            <div class="flex flex-col min-w-0 flex-1">
              <span class="text-[13px] font-medium truncate leading-tight text-[var(--color-foreground)]">
                {{ entry.display_name }}
              </span>
              <span class="text-[10px] font-mono text-[var(--color-foreground-subtle)] truncate leading-tight mt-0.5">
                {{ entry.type }}
              </span>
            </div>
          </li>
        </ul>
      </section>

      <div
        v-if="grouped.length === 0"
        class="px-3 py-6 text-center text-xs text-[var(--color-foreground-subtle)]"
      >
        No nodes match “{{ filter }}”.
      </div>
    </div>
  </aside>
</template>
