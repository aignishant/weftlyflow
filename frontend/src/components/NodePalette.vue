<script setup lang="ts">
// Collapsible list of node types grouped by category. Clicking an entry
// emits `select` so the parent adds a fresh node to the canvas.
//
// Keyboard support:
//   ↓ / ↑   move highlight among the flat filtered list (skips collapsed groups)
//   Enter   add the highlighted node
//   Esc     clear the search filter
//   /       focus the search input (scoped — palette only reacts when focused)

import { ChevronRight, Package, Search, Sparkles } from "lucide-vue-next";
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

const totalCount = computed(() => props.types.length);

function toggleCategory(cat: string): void {
  collapsed.value = { ...collapsed.value, [cat]: !collapsed.value[cat] };
}

// Palette of tone tokens per category — keeps a consistent visual hierarchy
// between the palette (left list), the template cards, and the run panel.
const CATEGORY_META: Record<
  string,
  { label: string; from: string; to: string; accent: string }
> = {
  trigger:     { label: "Triggers",     from: "#3dd28d", to: "#5c8dff", accent: "rgba(61, 210, 141, 0.28)" },
  core:        { label: "Core",         from: "#5c8dff", to: "#8b5cff", accent: "rgba(92, 141, 255, 0.28)" },
  integration: { label: "Integrations", from: "#f0b455", to: "#f76c6c", accent: "rgba(240, 180, 85, 0.28)" },
  ai:          { label: "AI",           from: "#8b5cff", to: "#f76cc6", accent: "rgba(139, 92, 255, 0.28)" },
  helpers:     { label: "Helpers",      from: "#6c7383", to: "#9aa3b2", accent: "rgba(154, 163, 178, 0.24)" },
  transform:   { label: "Transform",    from: "#55c8e6", to: "#3dd28d", accent: "rgba(85, 200, 230, 0.28)" },
  flow:        { label: "Flow",         from: "#5c8dff", to: "#3dd28d", accent: "rgba(92, 141, 255, 0.28)" },
};

function metaFor(cat: string): { label: string; from: string; to: string; accent: string } {
  return (
    CATEGORY_META[cat] ?? {
      label: cat.charAt(0).toUpperCase() + cat.slice(1),
      from: "#5c8dff",
      to: "#8b5cff",
      accent: "rgba(92, 141, 255, 0.22)",
    }
  );
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
    class="palette"
    data-testid="node-palette"
  >
    <header class="palette-head">
      <div class="palette-title">
        <span class="palette-logo">
          <Sparkles :size="13" />
        </span>
        <div class="palette-heading">
          <span class="palette-label">Nodes</span>
          <span class="palette-count">{{ totalCount }}</span>
        </div>
      </div>
      <div
        class="palette-search"
        data-testid="palette-search"
      >
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

    <div class="palette-body">
      <section
        v-for="[category, entries] in grouped"
        :key="category"
        class="pal-group"
      >
        <button
          type="button"
          class="pal-cat"
          :style="{
            '--cat-from': metaFor(category).from,
            '--cat-to': metaFor(category).to,
            '--cat-accent': metaFor(category).accent,
          }"
          @click="toggleCategory(category)"
        >
          <ChevronRight
            :class="cn(
              'pal-chev',
              !collapsed[category] && 'open',
            )"
          />
          <span class="pal-cat-dot" />
          <span class="pal-cat-label">{{ metaFor(category).label }}</span>
          <span class="pal-cat-count">{{ entries.length }}</span>
        </button>

        <ul
          v-show="!collapsed[category]"
          class="pal-list"
        >
          <li
            v-for="entry in entries"
            :key="entry.type"
            :data-testid="`palette-add-${entry.type}`"
            :class="cn(
              'pal-item',
              visibleEntries[highlightIndex]?.type === entry.type && 'highlighted',
            )"
            :style="{
              '--cat-from': metaFor(category).from,
              '--cat-to': metaFor(category).to,
              '--cat-accent': metaFor(category).accent,
            }"
            @click="emit('select', entry)"
          >
            <div class="pal-icon">
              <component
                :is="iconForNode(entry.type, entry.category)"
                class="h-3.5 w-3.5"
              />
            </div>
            <div class="pal-meta">
              <span class="pal-name">{{ entry.display_name }}</span>
              <span class="pal-slug">{{ entry.type }}</span>
            </div>
          </li>
        </ul>
      </section>

      <div
        v-if="grouped.length === 0"
        class="pal-empty"
      >
        <Package :size="18" />
        <p>No nodes match “{{ filter }}”.</p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.palette {
  display: flex;
  flex-direction: column;
  width: 272px;
  flex-shrink: 0;
  background:
    linear-gradient(180deg, rgba(28, 31, 44, 0.6), rgba(18, 20, 28, 0.6)),
    var(--color-surface, #161924);
  border-right: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.06));
  overflow: hidden;
  position: relative;
}

/* ---------- header ---------- */
.palette-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 12px 10px;
  border-bottom: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.06));
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent);
}
.palette-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.palette-logo {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  color: #0f1117;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  box-shadow: 0 6px 14px -6px rgba(92, 141, 255, 0.55),
              inset 0 0 0 1px rgba(255, 255, 255, 0.18);
  flex: 0 0 auto;
}
.palette-heading {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.palette-label {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--color-foreground, #ffffff);
}
.palette-count {
  font-size: 10.5px;
  font-weight: 600;
  color: #b9c5ff;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(92, 141, 255, 0.12);
  border: 1px solid rgba(92, 141, 255, 0.28);
}
.palette-search { width: 100%; }

/* ---------- body ---------- */
.palette-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0 12px;
  scrollbar-width: thin;
  scrollbar-color: rgba(92, 141, 255, 0.3) transparent;
}
.palette-body::-webkit-scrollbar { width: 8px; }
.palette-body::-webkit-scrollbar-thumb {
  background: rgba(92, 141, 255, 0.22);
  border-radius: 4px;
}

.pal-group { margin-bottom: 4px; }

/* sticky category header */
.pal-cat {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px 6px;
  background:
    linear-gradient(90deg, var(--cat-accent, rgba(92, 141, 255, 0.2)) 0%, transparent 60%),
    linear-gradient(180deg, rgba(18, 20, 28, 0.92), rgba(18, 20, 28, 0.78));
  border: none;
  border-bottom: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.06));
  cursor: pointer;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  color: var(--color-foreground-muted, #c4cad4);
  transition: color 0.15s ease, background 0.15s ease;
}
.pal-cat:hover { color: var(--color-foreground, #ffffff); }
.pal-chev {
  width: 11px;
  height: 11px;
  color: var(--color-foreground-subtle, #6c7383);
  transition: transform 0.15s ease;
  flex: 0 0 auto;
}
.pal-chev.open { transform: rotate(90deg); }
.pal-cat-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--cat-from, #5c8dff), var(--cat-to, #8b5cff));
  box-shadow: 0 0 0 3px var(--cat-accent, rgba(92, 141, 255, 0.2));
  flex: 0 0 auto;
}
.pal-cat-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.pal-cat-count {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 999px;
  color: var(--color-foreground-muted, #c4cad4);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
}

.pal-list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
}

.pal-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px 7px 14px;
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
}
.pal-item::before {
  content: "";
  position: absolute;
  inset: 4px 6px 4px 8px;
  border-radius: 8px;
  background: var(--cat-accent, rgba(92, 141, 255, 0.14));
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}
.pal-item:hover {
  border-left-color: var(--cat-from, #5c8dff);
  transform: translateX(1px);
}
.pal-item:hover::before { opacity: 0.55; }
.pal-item.highlighted {
  border-left-color: var(--cat-from, #5c8dff);
}
.pal-item.highlighted::before { opacity: 0.75; }

.pal-icon {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  color: #0f1117;
  background: linear-gradient(135deg, var(--cat-from, #5c8dff), var(--cat-to, #8b5cff));
  box-shadow: 0 6px 14px -8px var(--cat-from, rgba(92, 141, 255, 0.5)),
              inset 0 0 0 1px rgba(255, 255, 255, 0.18);
  flex: 0 0 auto;
}

.pal-meta {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
  gap: 2px;
}
.pal-name {
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--color-foreground, #ffffff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pal-slug {
  font-size: 10px;
  line-height: 1.2;
  color: var(--color-foreground-subtle, #8c93a1);
  font-family: var(--wf-font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 28px 12px;
  color: var(--color-foreground-subtle, #8c93a1);
  text-align: center;
}
.pal-empty p { margin: 0; font-size: 12px; }
</style>
