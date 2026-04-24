<script setup lang="ts">
// Minimal modal dialog. Backdrop + panel. No focus-trap (we only use
// this for the shortcut cheatsheet — a non-blocking, dismissable overlay).

import { X } from "lucide-vue-next";
import { onBeforeUnmount, onMounted, watch } from "vue";

const props = defineProps<{
  open: boolean;
  title?: string;
}>();

const emit = defineEmits<{
  (event: "update:open", value: boolean): void;
}>();

function close(): void {
  emit("update:open", false);
}

function onKey(event: KeyboardEvent): void {
  if (event.key === "Escape" && props.open) {
    close();
  }
}

onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

// Lock body scroll while open.
watch(
  () => props.open,
  (v) => {
    document.body.style.overflow = v ? "hidden" : "";
  },
);
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      enter-from-class="opacity-0"
      leave-active-class="transition-all duration-150 ease-in"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="fixed inset-0 z-50 bg-black/70 backdrop-blur-md flex items-start justify-center pt-24"
        @click.self="close"
      >
        <Transition
          appear
          enter-active-class="transition-all duration-200 ease-out"
          enter-from-class="opacity-0 scale-95 -translate-y-2"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition-all duration-150 ease-in"
          leave-from-class="opacity-100 scale-100"
          leave-to-class="opacity-0 scale-95"
        >
          <div
            v-if="open"
            class="w-full max-w-md rounded-[var(--radius-lg)] border border-[var(--color-border-subtle)] bg-[var(--color-surface)] text-[var(--color-foreground)] shadow-2xl ring-1 ring-white/5"
            role="dialog"
            aria-modal="true"
          >
            <header
              v-if="title"
              class="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border-subtle)]"
            >
              <h2 class="text-sm font-semibold">
                {{ title }}
              </h2>
              <button
                type="button"
                class="text-[var(--color-foreground-subtle)] hover:text-[var(--color-foreground)] transition-colors"
                aria-label="Close dialog"
                @click="close"
              >
                <X class="h-4 w-4" />
              </button>
            </header>
            <div class="px-4 py-3">
              <slot />
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>
