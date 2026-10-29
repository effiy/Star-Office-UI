<template>
  <div class="sbic">
    <div class="sbic-header">
      <span class="sbic-avatar">{{ bot.avatar || "🤖" }}</span>
      <div>
        <h3 class="sbic-name">{{ bot.name }}</h3>
        <span class="sbic-role">{{ bot.role }}</span>
      </div>
      <button class="sbic-close" @click="$emit('close')">✕</button>
    </div>
    <div class="sbic-body">
      <div class="sbic-row">
        <span class="sbic-label">状态</span>
        <span class="sbic-value" :class="`is-${bot.state}`">{{ stateLabel }}</span>
      </div>
      <div class="sbic-row" v-if="bot.detail">
        <span class="sbic-label">详情</span>
        <span class="sbic-value">{{ bot.detail }}</span>
      </div>
      <div class="sbic-row">
        <span class="sbic-label">楼层</span>
        <span class="sbic-value">{{ bot.floor }}</span>
      </div>
      <div class="sbic-row" v-if="bot.updatedAt">
        <span class="sbic-label">更新</span>
        <span class="sbic-value">{{ bot.updatedAt }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Bot } from "../stores/useBotStore";

const props = defineProps<{ bot: Bot }>();
defineEmits<{ close: [] }>();

const stateLabel = computed(() => ({
  idle: "空闲", writing: "写作中", researching: "研究中", executing: "执行中", syncing: "同步中", error: "出错",
}[props.bot.state]));
</script>

<style scoped>
.sbic { background: var(--so-panel-bg); border-radius: var(--so-radius-lg); overflow: hidden; }
.sbic-header {
  display: flex; align-items: center; gap: var(--so-gap-sm);
  padding: var(--so-padding); background: var(--so-glass-bg);
  border-bottom: 1px solid var(--so-panel-border);
}
.sbic-avatar { font-size: 32px; }
.sbic-name { font-size: var(--so-font-size-lg); font-weight: 700; margin: 0; }
.sbic-role { font-size: var(--so-font-size-sm); color: var(--so-ink-muted); }
.sbic-close { margin-left: auto; border: none; background: none; font-size: 18px; color: var(--so-ink-dim); cursor: pointer; padding: 4px; }
.sbic-body { padding: var(--so-padding); display: flex; flex-direction: column; gap: var(--so-gap-sm); }
.sbic-row { display: flex; justify-content: space-between; align-items: center; gap: var(--so-gap); }
.sbic-label { font-size: var(--so-font-size-sm); color: var(--so-ink-muted); flex-shrink: 0; }
.sbic-value { font-size: var(--so-font-size-sm); font-weight: 600; text-align: right; }
.sbic-value.is-executing { color: var(--so-success); }
.sbic-value.is-writing { color: var(--so-warning); }
.sbic-value.is-idle { color: var(--so-ink-dim); }
.sbic-value.is-offline { color: var(--so-danger); }
</style>
