<script setup lang="ts">
// Button primitive. Thin shadcn-vue-style wrapper: variants via CVA,
// size via CVA, plus `loading` prop that shows a spinner and disables
// the button without losing its width.

import { Loader2 } from "lucide-vue-next";
import { computed } from "vue";

import { cn } from "@/lib/utils";

type Variant = "default" | "primary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "icon";

const props = withDefaults(
  defineProps<{
    variant?: Variant;
    size?: Size;
    loading?: boolean;
    type?: "button" | "submit" | "reset";
    disabled?: boolean;
  }>(),
  { variant: "default", size: "md", loading: false, type: "button", disabled: false },
);

const classes = computed(() =>
  cn(
    "inline-flex items-center justify-center gap-2 font-medium transition-all duration-150",
    "rounded-[var(--radius-md)] border disabled:opacity-50 disabled:cursor-not-allowed",
    "focus-visible:outline-2 focus-visible:outline-[var(--color-accent)] focus-visible:outline-offset-2",
    "active:translate-y-px active:scale-[0.98]",
    {
      sm: "text-xs px-2.5 py-1 h-7",
      md: "text-sm px-3 py-1.5 h-8",
      icon: "h-8 w-8 p-0",
    }[props.size],
    {
      default:
        "bg-[var(--color-surface)] border-[var(--color-border-subtle)] text-[var(--color-foreground)] hover:border-[var(--color-accent)] hover:bg-[var(--color-surface-2)]",
      primary:
        "bg-gradient-to-b from-[var(--color-accent-hover)] to-[var(--color-accent)] border-[var(--color-accent)] text-[var(--color-accent-contrast)] font-semibold shadow-[0_1px_0_0_rgba(255,255,255,0.15)_inset] hover:shadow-[0_0_0_1px_var(--color-accent),0_8px_24px_-6px_var(--color-accent),0_1px_0_0_rgba(255,255,255,0.15)_inset] hover:-translate-y-px",
      ghost:
        "border-transparent bg-transparent text-[var(--color-foreground-muted)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-surface-2)]",
      danger:
        "bg-transparent border-[var(--color-danger)] text-[var(--color-danger)] hover:bg-[color-mix(in_srgb,var(--color-danger)_15%,transparent)] hover:shadow-[0_0_12px_-4px_var(--color-danger)]",
      outline:
        "bg-transparent border-[var(--color-border-strong)] text-[var(--color-foreground)] hover:border-[var(--color-accent)] hover:bg-[var(--color-surface-2)]",
    }[props.variant],
  ),
);
</script>

<template>
  <button
    :type="type"
    :class="classes"
    :disabled="disabled || loading"
  >
    <Loader2
      v-if="loading"
      class="h-3.5 w-3.5 animate-spin"
    />
    <slot />
  </button>
</template>
