<script setup lang="ts">
// Visual divider. `vertical` flips orientation. `inset` pulls in the
// ends a bit for inline use between button groups.

import { computed } from "vue";

import { cn } from "@/lib/utils";

const props = withDefaults(
  defineProps<{
    vertical?: boolean;
    inset?: boolean;
  }>(),
  { vertical: false, inset: false },
);

const classes = computed(() =>
  cn(
    "bg-[var(--color-border-subtle)]",
    props.vertical ? "w-px self-stretch" : "h-px w-full",
    props.inset && (props.vertical ? "my-1.5" : "mx-1.5"),
  ),
);
</script>

<template>
  <div
    role="separator"
    :aria-orientation="vertical ? 'vertical' : 'horizontal'"
    :class="classes"
  />
</template>
