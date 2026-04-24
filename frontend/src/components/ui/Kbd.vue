<script setup lang="ts">
// Keyboard shortcut hint. Use for `<Kbd>Cmd</Kbd> <Kbd>K</Kbd>` rows
// in the shortcut cheatsheet and inline hints on tooltips.
</script>

<template>
  <kbd
    class="inline-flex items-center justify-center min-w-[1.5rem] h-5 px-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface-2)] text-[10px] font-mono text-[var(--color-foreground-muted)]"
  >
    <slot />
  </kbd>
</template>
