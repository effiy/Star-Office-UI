<template>
  <Teleport to="body">
    <TransitionGroup name="toast" tag="div" class="so-toast-stack">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="so-toast"
        :class="`so-toast--${t.type}`"
        role="alert"
        @click="dismiss(t.id)"
      >
        <span class="so-toast__icon">{{ icons[t.type] }}</span>
        <span class="so-toast__text">{{ t.message }}</span>
      </div>
    </TransitionGroup>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * SoToast — Global toast notification bar
 *
 * Renders a stack of toast notifications managed by useToast().
 * Mount once in App.vue; any component can call useToast().show().
 *
 * Types: success | error | warning | info
 * Auto-dismiss: default 3s, 0 = persistent (click to dismiss)
 */
import { useToast } from "../../composables/useToast";

const { toasts, dismiss } = useToast();

const icons: Record<string, string> = {
  success: "✓",
  error: "✕",
  warning: "⚠",
  info: "ℹ",
};
</script>

<style scoped>
.so-toast-stack {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: var(--so-z-toast, 800);
  display: flex;
  flex-direction: column;
  gap: var(--so-gap-sm, 8px);
  max-width: 360px;
  pointer-events: none;
}

.so-toast {
  display: flex;
  align-items: center;
  gap: var(--so-gap-sm, 8px);
  padding: 10px 16px;
  background: var(--so-panel-bg, rgba(255, 255, 255, 0.95));
  backdrop-filter: var(--so-glass-blur, blur(6px));
  border: var(--so-border-width, 1px) solid var(--so-panel-border);
  border-radius: var(--so-radius, 8px);
  box-shadow: var(--so-shadow, 0 2px 8px rgba(0, 0, 0, 0.08));
  font-family: var(--so-font-pixel, monospace);
  font-size: var(--so-font-size-sm, 11px);
  color: var(--so-ink, #3d3929);
  cursor: pointer;
  pointer-events: auto;
  transition: all var(--so-transition, 0.2s ease);
}

.so-toast:hover {
  transform: translateX(-4px);
  box-shadow: var(--so-shadow-lg, 0 4px 16px rgba(0, 0, 0, 0.1));
}

/* ── Variant accent borders ── */
.so-toast--success {
  border-left: 3px solid var(--so-success, #67c23a);
}
.so-toast--error {
  border-left: 3px solid var(--so-danger, #f56c6c);
}
.so-toast--warning {
  border-left: 3px solid var(--so-warning, #e6a23c);
}
.so-toast--info {
  border-left: 3px solid var(--so-info, #409eff);
}

.so-toast__icon {
  font-size: var(--so-icon, 18px);
  flex-shrink: 0;
  line-height: 1;
}

.so-toast--success .so-toast__icon { color: var(--so-success); }
.so-toast--error   .so-toast__icon { color: var(--so-danger); }
.so-toast--warning .so-toast__icon { color: var(--so-warning); }
.so-toast--info    .so-toast__icon { color: var(--so-info); }

.so-toast__text {
  flex: 1;
  min-width: 0;
  line-height: var(--so-line-height-normal, 1.5);
}

/* ── Enter/Leave transitions ── */
.toast-enter-active {
  transition: all var(--so-duration, 200ms) var(--so-easing-decelerate);
}
.toast-leave-active {
  transition: all var(--so-duration-fast, 150ms) var(--so-easing-accelerate);
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>