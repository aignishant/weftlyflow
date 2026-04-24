<script setup lang="ts">
// Tour overlay — spotlight + popover driven by the reactive controller in
// src/lib/tour.ts. Mounts once in App.vue and shows whatever tour is
// currently active. Tracks the target element's bounding box in real time
// so it follows resizes/scrolls, and forwards Esc/Arrow keys to the
// controller for keyboard-first users.

import { ChevronLeft, ChevronRight, Sparkles, X } from "lucide-vue-next";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

import {
  currentStep,
  finishTour,
  isFirstStep,
  isLastStep,
  nextStep,
  previousStep,
  skipTour,
  stepNumber,
  totalSteps,
  tourState,
} from "@/lib/tour";

interface Rect { top: number; left: number; width: number; height: number }

const targetRect = ref<Rect | null>(null);
let rafId: number | null = null;
let resizeObs: ResizeObserver | null = null;
let mutObs: MutationObserver | null = null;
let onScroll: (() => void) | null = null;
let onResize: (() => void) | null = null;

const PADDING = 10;
const POPOVER_W = 340;
const POPOVER_H = 200;

const active = computed(() => tourState.active !== null);

function measure(): void {
  const step = currentStep.value;
  if (!step) {
    targetRect.value = null;
    return;
  }
  if (!step.target) {
    targetRect.value = null;
    return;
  }
  const el = document.querySelector<HTMLElement>(step.target);
  if (!el) {
    targetRect.value = null;
    return;
  }
  const r = el.getBoundingClientRect();
  targetRect.value = {
    top: r.top,
    left: r.left,
    width: r.width,
    height: r.height,
  };
  // Scroll target into view if off-screen.
  const vh = window.innerHeight;
  if (r.top < 80 || r.bottom > vh - 80) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function schedule(): void {
  if (rafId !== null) cancelAnimationFrame(rafId);
  rafId = requestAnimationFrame(() => {
    rafId = null;
    measure();
  });
}

function attach(): void {
  detach();
  onScroll = () => schedule();
  onResize = () => schedule();
  window.addEventListener("scroll", onScroll, true);
  window.addEventListener("resize", onResize);
  resizeObs = new ResizeObserver(() => schedule());
  resizeObs.observe(document.documentElement);
  mutObs = new MutationObserver(() => schedule());
  mutObs.observe(document.body, { childList: true, subtree: true });
}

function detach(): void {
  if (onScroll) window.removeEventListener("scroll", onScroll, true);
  if (onResize) window.removeEventListener("resize", onResize);
  onScroll = null;
  onResize = null;
  resizeObs?.disconnect();
  resizeObs = null;
  mutObs?.disconnect();
  mutObs = null;
  if (rafId !== null) cancelAnimationFrame(rafId);
  rafId = null;
}

watch(active, (isActive) => {
  if (isActive) {
    void nextTick(() => {
      measure();
      attach();
    });
  } else {
    detach();
    targetRect.value = null;
  }
});

watch(() => tourState.stepIndex, () => {
  void nextTick(() => measure());
});

onBeforeUnmount(() => detach());

function onKey(event: KeyboardEvent): void {
  if (!active.value) return;
  if (event.key === "Escape") {
    event.preventDefault();
    skipTour();
  } else if (event.key === "ArrowRight" || event.key === "Enter") {
    event.preventDefault();
    nextStep();
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    previousStep();
  }
}

watch(active, (v) => {
  if (v) window.addEventListener("keydown", onKey);
  else window.removeEventListener("keydown", onKey);
});

const spotlightStyle = computed(() => {
  const r = targetRect.value;
  if (!r) return { display: "none" };
  return {
    top: `${r.top - PADDING}px`,
    left: `${r.left - PADDING}px`,
    width: `${r.width + PADDING * 2}px`,
    height: `${r.height + PADDING * 2}px`,
  };
});

// Position the popover relative to the target rect.
const popoverStyle = computed<Record<string, string>>(() => {
  const step = currentStep.value;
  const r = targetRect.value;
  const vw = window.innerWidth || 1440;
  const vh = window.innerHeight || 900;
  if (!step || !r) {
    // Center on screen.
    return {
      top: `${Math.max(20, vh / 2 - POPOVER_H / 2)}px`,
      left: `${Math.max(20, vw / 2 - POPOVER_W / 2)}px`,
      width: `${POPOVER_W}px`,
    };
  }
  const placement = step.placement ?? "auto";
  const offset = step.offset ?? 16;
  let top = 0;
  let left = 0;

  const place = placement === "auto" ? autoPlacement(r, vw, vh) : placement;
  if (place === "bottom") {
    top = r.top + r.height + offset;
    left = r.left + r.width / 2 - POPOVER_W / 2;
  } else if (place === "top") {
    top = r.top - POPOVER_H - offset;
    left = r.left + r.width / 2 - POPOVER_W / 2;
  } else if (place === "right") {
    top = r.top + r.height / 2 - POPOVER_H / 2;
    left = r.left + r.width + offset;
  } else {
    top = r.top + r.height / 2 - POPOVER_H / 2;
    left = r.left - POPOVER_W - offset;
  }
  // Clamp into viewport.
  top = Math.max(16, Math.min(top, vh - POPOVER_H - 16));
  left = Math.max(16, Math.min(left, vw - POPOVER_W - 16));
  return {
    top: `${top}px`,
    left: `${left}px`,
    width: `${POPOVER_W}px`,
  };
});

function autoPlacement(r: Rect, vw: number, vh: number): "top" | "bottom" | "left" | "right" {
  const below = vh - (r.top + r.height);
  const above = r.top;
  const right = vw - (r.left + r.width);
  const left = r.left;
  const max = Math.max(below, above, right, left);
  if (max === below) return "bottom";
  if (max === above) return "top";
  if (max === right) return "right";
  return "left";
}

const progressPct = computed(() =>
  totalSteps.value === 0 ? 0 : Math.round((stepNumber.value / totalSteps.value) * 100),
);
</script>

<template>
  <transition name="tour-fade">
    <div
      v-if="active && currentStep"
      class="tour-root"
      data-testid="tour-overlay"
    >
      <!-- Dimmed backdrop with a cut-out over the target -->
      <div class="tour-mask">
        <div class="mask-piece mask-top" />
        <div class="mask-piece mask-bottom" />
        <div class="mask-piece mask-left" />
        <div class="mask-piece mask-right" />
      </div>

      <div
        v-if="targetRect"
        class="tour-ring"
        :style="spotlightStyle"
      />

      <!-- Popover -->
      <div
        class="tour-popover"
        role="dialog"
        aria-modal="true"
        :style="popoverStyle"
      >
        <header class="tp-head">
          <span class="tp-pill">
            <Sparkles :size="11" /> Tour · {{ stepNumber }}/{{ totalSteps }}
          </span>
          <button
            class="tp-close"
            data-testid="tour-skip"
            aria-label="Skip tour"
            @click="skipTour"
          >
            <X :size="14" />
          </button>
        </header>
        <h3 class="tp-title">
          {{ currentStep.title }}
        </h3>
        <p class="tp-body">
          {{ currentStep.body }}
        </p>
        <div
          class="tp-progress"
          aria-hidden="true"
        >
          <div
            class="tp-progress-bar"
            :style="{ width: `${progressPct}%` }"
          />
        </div>
        <footer class="tp-foot">
          <button
            class="tp-ghost"
            data-testid="tour-skip-footer"
            @click="skipTour"
          >
            Skip
          </button>
          <div class="tp-spacer" />
          <button
            v-if="!isFirstStep"
            class="tp-ghost"
            data-testid="tour-back"
            @click="previousStep"
          >
            <ChevronLeft :size="14" /> Back
          </button>
          <button
            v-if="!isLastStep"
            class="tp-primary"
            data-testid="tour-next"
            @click="nextStep"
          >
            Next <ChevronRight :size="14" />
          </button>
          <button
            v-else
            class="tp-primary"
            data-testid="tour-finish"
            @click="finishTour"
          >
            Got it
          </button>
        </footer>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.tour-root {
  position: fixed;
  inset: 0;
  z-index: 9000;
  pointer-events: none;
}

/* Four-panel mask around the spotlight. Each panel is always present;
   when there's no target rect, the four panels collapse into one. */
.tour-mask {
  position: absolute;
  inset: 0;
  pointer-events: auto;
}
.mask-piece {
  position: absolute;
  background: rgba(7, 9, 14, 0.72);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}
.mask-top    { inset: 0 0 auto 0; height: 100%; }
.mask-bottom, .mask-left, .mask-right { display: none; }

.tour-ring {
  position: absolute;
  border-radius: 14px;
  box-shadow:
    0 0 0 9999px rgba(7, 9, 14, 0.72),
    0 0 0 2px rgba(92, 141, 255, 0.65),
    0 0 40px 6px rgba(92, 141, 255, 0.35);
  transition: top 0.2s ease, left 0.2s ease, width 0.2s ease, height 0.2s ease;
  pointer-events: none;
  /* Hide the fallback mask when the ring is active (box-shadow does the dim). */
}
/* When ring is visible, hide the flat mask. */
.tour-ring ~ .tour-mask { opacity: 0; }

.tour-popover {
  position: absolute;
  pointer-events: auto;
  min-height: 168px;
  padding: 16px 16px 14px 16px;
  border-radius: 14px;
  background:
    linear-gradient(180deg, rgba(28, 31, 44, 0.96), rgba(22, 25, 36, 0.96));
  border: 1px solid rgba(92, 141, 255, 0.35);
  box-shadow:
    0 30px 80px -30px rgba(92, 141, 255, 0.5),
    0 0 0 1px rgba(255, 255, 255, 0.04) inset;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  color: var(--wf-text, #e7eaf3);
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: top 0.2s ease, left 0.2s ease;
}
.tour-popover::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 14px;
  padding: 1px;
  background: linear-gradient(135deg, rgba(92,141,255,0.55), transparent 45%, rgba(139,92,255,0.55));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.tp-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tp-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #b9c5ff;
  padding: 4px 8px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(92,141,255,0.22), rgba(139,92,255,0.18));
  border: 1px solid rgba(92, 141, 255, 0.35);
}
.tp-close {
  margin-left: auto;
  display: inline-grid;
  place-items: center;
  width: 22px; height: 22px;
  border-radius: 6px;
  color: var(--wf-text-muted, #9aa3b2);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  padding: 0;
}
.tp-close:hover { background: rgba(255,255,255,0.06); color: #e7eaf3; }

.tp-title {
  margin: 2px 0 0 0;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.01em;
  background: linear-gradient(90deg, #e7eaf3, #b9c5ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.tp-body {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--wf-text-muted, #9aa3b2);
}

.tp-progress {
  height: 3px;
  margin: 4px 0 2px 0;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.tp-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #5c8dff, #8b5cff);
  transition: width 0.25s ease;
  box-shadow: 0 0 10px rgba(92,141,255,0.6);
}

.tp-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}
.tp-spacer { flex: 1; }
.tp-ghost, .tp-primary {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 11px;
  border-radius: 9px;
  cursor: pointer;
  border: 1px solid var(--wf-border, #262a36);
  background: rgba(255,255,255,0.02);
  color: var(--wf-text-muted, #9aa3b2);
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease, transform 0.12s ease;
}
.tp-ghost:hover { color: #e7eaf3; border-color: rgba(92,141,255,0.4); background: rgba(255,255,255,0.04); }
.tp-primary {
  color: #0f1117;
  background: linear-gradient(135deg, #5c8dff, #8b5cff);
  border-color: transparent;
  box-shadow: 0 10px 24px -12px rgba(92,141,255,0.65);
}
.tp-primary:hover { transform: translateY(-1px); filter: brightness(1.05); }

/* Fade transition */
.tour-fade-enter-active, .tour-fade-leave-active { transition: opacity 0.2s ease; }
.tour-fade-enter-from, .tour-fade-leave-to { opacity: 0; }
</style>
