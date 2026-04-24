<script setup lang="ts">
// Custom Vue Flow node renderer. Registered once in Editor.vue via
// `:node-types="{ workflow: WorkflowNodeCard }"` so every workflow node
// type renders with our card rather than the default white rectangle.
//
// Data contract (see Editor.vue's `flowNodes` computed):
//   {
//     label: string      // display name, user-editable
//     slug: string       // e.g. "weftlyflow.http_request"
//     category?: string  // "trigger" | "core" | "integration" | "ai"
//     status?: "idle" | "success" | "error" | "running"
//     disabled?: boolean
//   }

import { Handle, Position } from "@vue-flow/core";
import { computed } from "vue";

import { cn } from "@/lib/utils";
import { iconForNode } from "@/lib/node-icons";

type Status = "idle" | "success" | "error" | "running";

const props = defineProps<{
  id: string;
  selected: boolean;
  data: {
    label: string;
    slug: string;
    category?: string;
    status?: Status;
    disabled?: boolean;
  };
}>();

const icon = computed(() => iconForNode(props.data.slug, props.data.category));

const status = computed<Status>(() => props.data.status ?? "idle");

const wrapperClasses = computed(() =>
  cn(
    "group relative flex items-center gap-2.5 min-w-[180px] max-w-[240px] px-3 py-2.5",
    "rounded-[var(--radius-md)] border bg-[var(--color-surface)]",
    "text-[var(--color-foreground)] shadow-sm transition-all duration-200",
    "hover:border-[var(--color-accent)] hover:-translate-y-px hover:shadow-md",
    props.selected
      ? "border-[var(--color-accent)] shadow-[0_0_0_2px_var(--color-accent),0_12px_32px_-12px_var(--color-accent)]"
      : "border-[var(--color-border-subtle)]",
    status.value === "running" &&
      "shadow-[0_0_0_2px_color-mix(in_srgb,var(--color-accent)_60%,transparent),0_0_24px_-6px_var(--color-accent)]",
    status.value === "error" &&
      "border-[var(--color-danger)] shadow-[0_0_0_1px_var(--color-danger)]",
    status.value === "success" &&
      !props.selected &&
      "border-[color-mix(in_srgb,var(--color-success)_50%,var(--color-border-subtle))]",
    props.data.disabled && "opacity-50",
  ),
);

const iconTileClasses = computed(() =>
  cn(
    "flex items-center justify-center h-8 w-8 rounded-[var(--radius-sm)] border transition-all duration-200 shrink-0",
    status.value === "running"
      ? "bg-[color-mix(in_srgb,var(--color-accent)_15%,var(--color-surface-2))] border-[var(--color-accent)] text-[var(--color-accent)]"
      : "bg-[var(--color-surface-2)] border-[var(--color-border-subtle)] text-[var(--color-foreground-muted)] group-hover:text-[var(--color-accent)]",
  ),
);

const statusDotClasses = computed(() =>
  cn(
    "h-2 w-2 rounded-full shrink-0",
    {
      idle: "bg-[var(--color-foreground-subtle)]",
      success: "bg-[var(--color-success)] shadow-[0_0_6px_0_var(--color-success)]",
      error: "bg-[var(--color-danger)] shadow-[0_0_6px_0_var(--color-danger)]",
      running: "bg-[var(--color-accent)] animate-pulse shadow-[0_0_8px_0_var(--color-accent)]",
    }[status.value],
  ),
);

const handleBaseClasses =
  "!w-2.5 !h-2.5 !bg-[var(--color-surface)] !border-2 !border-[var(--color-border-strong)] " +
  "hover:!border-[var(--color-accent)] !transition-colors";
</script>

<template>
  <div :class="wrapperClasses">
    <!-- Input handle (left edge) -->
    <Handle
      id="main"
      type="target"
      :position="Position.Left"
      :class="handleBaseClasses"
    />

    <!-- Icon tile -->
    <div :class="iconTileClasses">
      <component
        :is="icon"
        class="h-4 w-4"
      />
    </div>

    <!-- Name + slug -->
    <div class="flex flex-col min-w-0 flex-1">
      <span class="text-sm font-medium truncate leading-tight">
        {{ data.label }}
      </span>
      <span
        class="text-[10px] font-mono text-[var(--color-foreground-subtle)] truncate leading-tight mt-0.5"
      >
        {{ data.slug }}
      </span>
    </div>

    <!-- Status dot -->
    <span
      :class="statusDotClasses"
      :title="data.status ?? 'idle'"
    />

    <!-- Output handle (right edge) -->
    <Handle
      id="main"
      type="source"
      :position="Position.Right"
      :class="handleBaseClasses"
    />
  </div>
</template>
