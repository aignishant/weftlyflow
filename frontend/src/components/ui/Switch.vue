<script setup lang="ts">
// Toggle switch. Native <button role="switch"> so screen readers and
// Playwright can click/press it. Animated handle slides via transform.

import { computed } from "vue";

import { cn } from "@/lib/utils";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    disabled?: boolean;
    loading?: boolean;
    /** Accessible label when there's no adjacent text. */
    ariaLabel?: string;
    size?: "sm" | "md";
  }>(),
  { disabled: false, loading: false, ariaLabel: undefined, size: "md" },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
}>();

const trackClasses = computed(() =>
  cn(
    "relative inline-flex shrink-0 items-center rounded-full border transition-colors",
    "focus-visible:outline-2 focus-visible:outline-[var(--color-accent)] focus-visible:outline-offset-2",
    "disabled:opacity-50 disabled:cursor-not-allowed",
    {
      sm: "h-4 w-7",
      md: "h-5 w-9",
    }[props.size],
    props.modelValue
      ? "bg-[var(--color-accent)] border-[var(--color-accent)] shadow-[0_0_12px_-2px_var(--color-accent)]"
      : "bg-[var(--color-surface-2)] border-[var(--color-border-strong)]",
  ),
);

const thumbClasses = computed(() =>
  cn(
    "inline-block rounded-full bg-white shadow-md transform transition-transform duration-200 ease-out",
    {
      sm: "h-3 w-3",
      md: "h-4 w-4",
    }[props.size],
    props.modelValue
      ? { sm: "translate-x-3.5", md: "translate-x-4" }[props.size]
      : "translate-x-0.5",
  ),
);

function onToggle(): void {
  if (props.disabled || props.loading) return;
  emit("update:modelValue", !props.modelValue);
}
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="ariaLabel"
    :disabled="disabled || loading"
    :class="trackClasses"
    @click="onToggle"
  >
    <span :class="thumbClasses" />
  </button>
</template>
