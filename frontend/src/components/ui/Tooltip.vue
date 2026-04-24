<script setup lang="ts">
// CSS-only tooltip. Wraps a single child and shows a label on hover /
// focus-within after a short delay. Positions itself relative to the
// wrapper using absolute positioning — no Teleport, no popper, no JS
// measurement. Good enough for labels on icon buttons.
//
// Usage:
//   <Tooltip content="Save (⌘S)">
//     <Button ...>
//   </Tooltip>

import { computed } from "vue";

import { cn } from "@/lib/utils";

type Side = "top" | "bottom" | "left" | "right";

const props = withDefaults(
  defineProps<{
    content: string;
    side?: Side;
    /** Delay before the tooltip appears, in ms. */
    delay?: number;
  }>(),
  { side: "bottom", delay: 300 },
);

const tooltipClasses = computed(() =>
  cn(
    "pointer-events-none absolute z-50 whitespace-nowrap rounded-[var(--radius-sm)]",
    "bg-[var(--color-surface-2)] border border-[var(--color-border-strong)]",
    "px-2 py-1 text-[11px] font-medium text-[var(--color-foreground)] shadow-lg",
    "opacity-0 scale-95 transition-all duration-150",
    "group-hover/tooltip:opacity-100 group-hover/tooltip:scale-100",
    "group-focus-within/tooltip:opacity-100 group-focus-within/tooltip:scale-100",
    {
      top: "bottom-full left-1/2 -translate-x-1/2 mb-1.5",
      bottom: "top-full left-1/2 -translate-x-1/2 mt-1.5",
      left: "right-full top-1/2 -translate-y-1/2 mr-1.5",
      right: "left-full top-1/2 -translate-y-1/2 ml-1.5",
    }[props.side],
  ),
);

const delayStyle = computed(() => `transition-delay: ${props.delay}ms`);
</script>

<template>
  <span class="group/tooltip relative inline-flex">
    <slot />
    <span
      role="tooltip"
      :class="tooltipClasses"
      :style="delayStyle"
    >
      {{ content }}
    </span>
  </span>
</template>
