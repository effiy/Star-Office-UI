<template>
  <Teleport to="body">
    <Transition name="tooltip-pop">
      <div
        v-if="visible"
        ref="tooltipRef"
        class="so-tooltip"
        :class="`so-tooltip--${placement}`"
        :style="positionStyle"
      >
        <!-- Header row: icon + title -->
        <div class="so-tooltip__header">
          <span v-if="icon" class="so-tooltip__icon">{{ icon }}</span>
          <span class="so-tooltip__title">{{ title }}</span>
        </div>

        <!-- Redlines -->
        <ul v-if="redlines && redlines.length" class="so-tooltip__redlines">
          <li v-for="(line, i) in redlines" :key="i" class="so-tooltip__redline">
            <span class="so-tooltip__bullet">•</span>
            {{ line }}
          </li>
        </ul>

        <!-- Slot for custom content -->
        <div v-if="$slots.default" class="so-tooltip__extra">
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * SoTooltip — Reusable tooltip for role cards and hover info
 *
 * Usage: <SoTooltip :visible="hovering" :title="roleTitle" :icon="icon"
 *                    :redlines="redlines" :target="el" />
 *
 * Props:
 * - visible: show/hide
 * - title: main text (e.g. role title from YiAi)
 * - icon: optional emoji/icon
 * - redlines: optional array of rule strings
 * - placement: "top" | "bottom" | "right" (default: "right")
 * - target: the DOM element to position against
 */
import { computed, ref } from "vue";

const props = withDefaults(
  defineProps<{
    visible: boolean;
    title: string;
    icon?: string;
    redlines?: string[];
    placement?: "top" | "bottom" | "right";
    target?: HTMLElement | null;
    /** Manual position override (px from viewport top-left) */
    x?: number;
    y?: number;
  }>(),
  { placement: "right", icon: "", redlines: () => [] }
);

const tooltipRef = ref<HTMLElement>();

const positionStyle = computed(() => {
  if (props.x !== undefined && props.y !== undefined) {
    return { left: `${props.x}px`, top: `${props.y}px` };
  }
  if (props.target) {
    const rect = props.target.getBoundingClientRect();
    switch (props.placement) {
      case "top":
        return { left: `${rect.left + rect.width / 2}px`, top: `${rect.top - 8}px` };
      case "bottom":
        return { left: `${rect.left + rect.width / 2}px`, top: `${rect.bottom + 8}px` };
      case "right":
      default:
        return { left: `${rect.right + 12}px`, top: `${rect.top}px` };
    }
  }
  return {};
});
</script>

<style scoped>
.so-tooltip {
  position: fixed;
  z-index: var(--so-z-bubble, 50);
  max-width: 220px;
  padding: 10px 14px;
  background: var(--so-panel-bg, rgba(255, 255, 255, 0.95));
  backdrop-filter: var(--so-glass-blur, blur(6px));
  border: var(--so-border-width, 1px) solid var(--so-panel-border);
  border-radius: var(--so-radius, 8px);
  box-shadow: var(--so-shadow-lg, 0 4px 16px rgba(0, 0, 0, 0.1));
  font-family: var(--so-font-pixel, monospace);
  pointer-events: none;
}

.so-tooltip--right { transform: translateY(-50%); }
.so-tooltip--top   { transform: translate(-50%, -100%); }
.so-tooltip--bottom{ transform: translateX(-50%); }

.so-tooltip__header {
  display: flex;
  align-items: center;
  gap: var(--so-gap-xs, 4px);
  margin-bottom: var(--so-gap-xs, 4px);
  padding-bottom: var(--so-gap-xs, 4px);
  border-bottom: 1px solid var(--so-panel-border);
}

.so-tooltip__icon {
  font-size: var(--so-icon, 18px);
  line-height: 1;
}

.so-tooltip__title {
  font-size: var(--so-font-size-sm, 11px);
  font-weight: var(--so-font-weight-bold, 700);
  color: var(--so-ink, #3d3929);
}

.so-tooltip__redlines {
  list-style: none;
  padding: 0;
  margin: 0;
}

.so-tooltip__redline {
  font-size: 10px;
  color: var(--so-ink-muted, #6b6560);
  line-height: var(--so-line-height-tight, 1.2);
  padding: 1px 0;
}

.so-tooltip__bullet {
  color: var(--so-accent, #d4c5b9);
  margin-right: 4px;
}

.so-tooltip__extra {
  margin-top: var(--so-gap-xs, 4px);
  padding-top: var(--so-gap-xs, 4px);
  border-top: 1px solid var(--so-panel-border);
}

/* ── Transition ── */
.tooltip-pop-enter-active {
  transition: all var(--so-duration, 200ms) var(--so-easing-decelerate);
}
.tooltip-pop-leave-active {
  transition: all var(--so-duration-fast, 150ms) var(--so-easing-accelerate);
}
.tooltip-pop-enter-from,
.tooltip-pop-leave-to {
  opacity: 0;
  transform: translateX(-4px) translateY(-50%) scale(0.95);
}
</style>