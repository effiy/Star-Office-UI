<template>
  <button
    class="sba"
    :class="{
      'is-selected': selected,
      [`is-${bot.state}`]: true,
    }"
    @click="$emit('click')"
  >
    <span class="sba-avatar">{{ bot.avatar || "🤖" }}</span>
    <span class="sba-name">{{ bot.name }}</span>
    <span class="sba-dot" />
  </button>
</template>

<script setup lang="ts">
import type { Bot } from "../stores/useBotStore";

defineProps<{ bot: Bot; selected?: boolean }>();
defineEmits<{ click: [] }>();
</script>

<style scoped>
.sba {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border: 1px solid var(--so-panel-border);
  border-radius: var(--so-radius); background: var(--so-glass-bg);
  cursor: pointer; transition: all var(--so-transition); position: relative;
}
.sba:hover { border-color: var(--so-accent); transform: translateY(-1px); }
.sba.is-selected { border-color: var(--so-ink); box-shadow: 0 0 0 1px var(--so-ink); }
.sba-avatar { font-size: 18px; line-height: 1; }
.sba-name { font-size: var(--so-font-size-sm); color: var(--so-ink-muted); }
.sba-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  transition: background 0.35s ease, box-shadow 0.35s ease;
}
.sba.is-executing .sba-dot { background: var(--so-success); box-shadow: 0 0 6px var(--so-success); animation: sba-pulse 1.6s ease infinite; }
.sba.is-writing .sba-dot { background: var(--so-warning); box-shadow: 0 0 6px var(--so-warning); animation: sba-pulse 1.2s ease infinite; }
.sba.is-idle .sba-dot { background: var(--so-ink-muted); }
.sba.is-offline .sba-dot { background: transparent; border: 1px solid var(--so-ink-dim); }
@keyframes sba-pulse { 0%,100%{transform:scale(1);opacity:1;} 50%{transform:scale(1.4);opacity:.5;} }
</style>
