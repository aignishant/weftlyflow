<script setup lang="ts">
// Card container. Use with optional <CardHeader>, <CardContent>,
// <CardFooter> children, or just drop freeform markup inside. The
// component itself is the bordered surface.

import { computed } from "vue";

import { cn } from "@/lib/utils";

const props = defineProps<{
  interactive?: boolean;
  selected?: boolean;
}>();

const classes = computed(() =>
  cn(
    "rounded-[var(--radius-md)] border bg-[var(--color-surface)] text-[var(--color-foreground)]",
    "transition-colors",
    props.interactive &&
      "cursor-pointer hover:border-[var(--color-accent)]",
    props.selected
      ? "border-[var(--color-accent)] shadow-[0_0_0_1px_var(--color-accent)]"
      : "border-[var(--color-border-subtle)]",
  ),
);
</script>

<template>
  <div :class="classes">
    <slot />
  </div>
</template>
