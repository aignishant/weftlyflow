<script setup lang="ts">
// Fixed bottom-right stack of toasts. Mount ONCE at the app root.
// Dismiss on click-through-X. Uses <TransitionGroup> for slide+fade.

import { AlertCircle, CheckCircle2, Info, X } from "lucide-vue-next";
import { computed } from "vue";

import { cn } from "@/lib/utils";
import { toast, toasts, type ToastVariant } from "@/lib/toast";

const items = computed(() => toasts.toasts);

const ICONS: Record<ToastVariant, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

const VARIANT_CLASSES: Record<ToastVariant, string> = {
  success:
    "border-[var(--color-success)] text-[var(--color-success)] bg-[color-mix(in_srgb,var(--color-success)_12%,var(--color-surface))]",
  error:
    "border-[var(--color-danger)] text-[var(--color-danger)] bg-[color-mix(in_srgb,var(--color-danger)_12%,var(--color-surface))]",
  info:
    "border-[var(--color-accent)] text-[var(--color-accent)] bg-[color-mix(in_srgb,var(--color-accent)_12%,var(--color-surface))]",
};

function cardClasses(variant: ToastVariant): string {
  return cn(
    "pointer-events-auto flex items-start gap-2.5 min-w-[280px] max-w-sm rounded-[var(--radius-md)] border px-3 py-2.5 shadow-2xl backdrop-blur-sm",
    VARIANT_CLASSES[variant],
  );
}
</script>

<template>
  <Teleport to="body">
    <div
      class="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2"
      data-testid="toast-container"
    >
      <TransitionGroup
        enter-active-class="transition-all duration-200 ease-out"
        enter-from-class="opacity-0 translate-x-4"
        enter-to-class="opacity-100 translate-x-0"
        leave-active-class="transition-all duration-150 ease-in absolute"
        leave-from-class="opacity-100 translate-x-0"
        leave-to-class="opacity-0 translate-x-4"
      >
        <div
          v-for="item in items"
          :key="item.id"
          :class="cardClasses(item.variant)"
          role="status"
          :data-testid="`toast-${item.variant}`"
        >
          <component
            :is="ICONS[item.variant]"
            class="h-4 w-4 mt-0.5 shrink-0"
          />
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold m-0 text-[var(--color-foreground)]">
              {{ item.title }}
            </p>
            <p
              v-if="item.description"
              class="text-xs mt-0.5 m-0 text-[var(--color-foreground-muted)]"
            >
              {{ item.description }}
            </p>
          </div>
          <button
            type="button"
            class="shrink-0 text-[var(--color-foreground-subtle)] hover:text-[var(--color-foreground)] transition-colors"
            aria-label="Dismiss"
            @click="toast.dismiss(item.id)"
          >
            <X class="h-3.5 w-3.5" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>
