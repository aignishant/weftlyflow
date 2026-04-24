// Shared utility helpers — kept to one-liners. Anything larger should
// earn its own module.

import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind class names with correct precedence (later classes win
 * over earlier ones even when they target the same utility bucket).
 * This is the canonical shadcn-vue `cn()` helper.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
