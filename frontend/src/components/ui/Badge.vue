<script setup lang="ts">
// Status pill. `variant` drives colour; `dot` adds a small leading
// indicator circle (optionally animated via `pulse`).

import { computed } from "vue";

import { cn } from "@/lib/utils";

type Variant =
  | "default"
  | "success"
  | "warning"
  | "danger"
  | "accent"
  | "muted";

const props = withDefaults(
  defineProps<{
    variant?: Variant;
    dot?: boolean;
    pulse?: boolean;
  }>(),
  { variant: "default", dot: false, pulse: false },
);

const wrapperClasses = computed(() =>
  cn(
    "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider",
    {
      default:
        "bg-[color-mix(in_srgb,var(--color-foreground-muted)_15%,transparent)] text-[var(--color-foreground-muted)]",
      success:
        "bg-[color-mix(in_srgb,var(--color-success)_15%,transparent)] text-[var(--color-success)]",
      warning:
        "bg-[color-mix(in_srgb,var(--color-warning)_15%,transparent)] text-[var(--color-warning)]",
      danger:
        "bg-[color-mix(in_srgb,var(--color-danger)_15%,transparent)] text-[var(--color-danger)]",
      accent:
        "bg-[color-mix(in_srgb,var(--color-accent)_15%,transparent)] text-[var(--color-accent)]",
      muted:
        "bg-[var(--color-surface-2)] text-[var(--color-foreground-subtle)]",
    }[props.variant],
  ),
);

const dotClasses = computed(() =>
  cn(
    "h-1.5 w-1.5 rounded-full bg-current",
    props.pulse && "animate-pulse",
  ),
);
</script>

<template>
  <span :class="wrapperClasses">
    <span
      v-if="dot"
      :class="dotClasses"
    />
    <slot />
  </span>
</template>
