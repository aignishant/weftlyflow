// Module-level toast store. Reactive array of active toasts, consumed
// by `<ToastContainer>` mounted once at the app root. Call `toast.success`
// / `toast.error` / `toast.info` from anywhere.

import { reactive } from "vue";

export type ToastVariant = "success" | "error" | "info";

export interface Toast {
  id: number;
  variant: ToastVariant;
  title: string;
  description?: string;
  /** Auto-dismiss in ms. `null` = sticky. */
  duration: number | null;
}

const state = reactive<{ toasts: Toast[] }>({ toasts: [] });

let nextId = 1;

function push(
  variant: ToastVariant,
  title: string,
  description?: string,
  duration: number | null = 3500,
): number {
  const id = nextId++;
  state.toasts.push({ id, variant, title, description, duration });
  if (duration !== null) {
    window.setTimeout(() => dismiss(id), duration);
  }
  return id;
}

function dismiss(id: number): void {
  const idx = state.toasts.findIndex((t) => t.id === id);
  if (idx >= 0) {
    state.toasts.splice(idx, 1);
  }
}

export const toasts = state;

export const toast = {
  success: (title: string, description?: string) =>
    push("success", title, description),
  error: (title: string, description?: string) =>
    push("error", title, description, 6000),
  info: (title: string, description?: string) => push("info", title, description),
  dismiss,
};
