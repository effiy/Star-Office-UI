<template>
  <Transition name="bubble-pop">
    <div v-if="visible" class="sbb" :class="[`sbb--${side}`]">
      <span class="sbb-avatar">{{ bot.avatar || "🤖" }}</span>
      <div class="sbb-body">
        <span class="sbb-name">{{ bot.name }}</span>
        <p class="sbb-text">{{ bot.detail || "空闲中" }}</p>
      </div>
      <button class="sbb-close" @click="$emit('close')">×</button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import type { Bot } from "../stores/useBotStore";

withDefaults(defineProps<{
  bot: Bot;
  visible?: boolean;
  side?: "left" | "right";
}>(), { visible: true, side: "right" });

defineEmits<{ close: [] }>();
</script>

<style scoped>
.sbb {
  display: flex; align-items: flex-start; gap: 8px;
  max-width: 260px; padding: 10px; background: var(--so-panel-bg);
  backdrop-filter: var(--so-glass-blur); border: 1px solid var(--so-panel-border);
  border-radius: var(--so-radius-lg); box-shadow: var(--so-shadow);
  position: absolute; z-index: 50;
}
.sbb--left { left: 0; }
.sbb--right { right: 0; }
.sbb-avatar { font-size: 20px; flex-shrink: 0; }
.sbb-body { flex: 1; min-width: 0; }
.sbb-name { font-size: var(--so-font-size-sm); font-weight: 700; color: var(--so-ink); }
.sbb-text { font-size: var(--so-font-size-sm); color: var(--so-ink-muted); margin-top: 2px; line-height: 1.4; }
.sbb-close { border: none; background: none; font-size: 16px; color: var(--so-ink-dim); cursor: pointer; padding: 0 2px; }
.bubble-pop-enter-active { transition: all 0.25s ease; }
.bubble-pop-leave-active { transition: all 0.2s ease; }
.bubble-pop-enter-from, .bubble-pop-leave-to { opacity: 0; transform: translateY(6px) scale(0.95); }
</style>
