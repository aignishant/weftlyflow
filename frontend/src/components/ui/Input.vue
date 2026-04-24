<script setup lang="ts">
// Input primitive. Mirrors native <input> attributes and forwards v-model
// via `modelValue` / `update:modelValue`. Supports leading/trailing slots
// for icons, plus `error` / `hint` props that render a helper line below.

import { AlertCircle } from "lucide-vue-next";
import { computed, useSlots } from "vue";

import { cn } from "@/lib/utils";

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    type?: string;
    placeholder?: string;
    disabled?: boolean;
    size?: "sm" | "md";
    /** Inline error message; switches border+hint to danger colors. */
    error?: string;
    /** Neutral helper text shown below when there's no error. */
    hint?: string;
  }>(),
  {
    type: "text",
    modelValue: "",
    size: "md",
    disabled: false,
    placeholder: "",
    error: "",
    hint: "",
  },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: string): void;
}>();

const slots = useSlots();
const hasLeading = computed(() => Boolean(slots.leading));
const hasError = computed(() => Boolean(props.error));

const wrapperClasses = computed(() =>
  cn(
    "flex items-center gap-2 rounded-[var(--radius-md)] border transition-all duration-150",
    "bg-[var(--color-bg)]",
    hasError.value
      ? "border-[var(--color-danger)] focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-danger)_25%,transparent)]"
      : "border-[var(--color-border-subtle)] focus-within:border-[var(--color-accent)] focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_20%,transparent)]",
    props.disabled && "opacity-50 cursor-not-allowed",
    {
      sm: "px-2 h-7 text-xs",
      md: "px-2.5 h-8 text-sm",
    }[props.size],
  ),
);

function onInput(event: Event): void {
  const target = event.target as HTMLInputElement;
  emit("update:modelValue", target.value);
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <div :class="wrapperClasses">
      <span
        v-if="hasLeading"
        class="flex items-center text-[var(--color-foreground-subtle)]"
      >
        <slot name="leading" />
      </span>
      <input
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :aria-invalid="hasError"
        class="flex-1 min-w-0 bg-transparent border-0 outline-none text-[var(--color-foreground)] placeholder:text-[var(--color-foreground-subtle)]"
        @input="onInput"
      >
      <slot name="trailing" />
    </div>
    <p
      v-if="error"
      class="flex items-center gap-1 text-[11px] text-[var(--color-danger)] m-0"
      role="alert"
    >
      <AlertCircle class="h-3 w-3 shrink-0" />
      {{ error }}
    </p>
    <p
      v-else-if="hint"
      class="text-[11px] text-[var(--color-foreground-subtle)] m-0"
    >
      {{ hint }}
    </p>
  </div>
</template>
