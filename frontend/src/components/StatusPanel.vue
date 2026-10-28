<template>
  <div class="ssp" :class="{ 'ssp--compact': compact }">
    <div class="ssp-header">
      <span class="ssp-title">Star 状态</span>
      <span class="ssp-badge ssp-badge--online">{{ botStore.onlineCount }} 在线</span>
    </div>
    <div class="ssp-bots">
      <BotAvatar
        v-for="bot in botStore.botsOnCurrentFloor"
        :key="bot.id"
        :bot="bot"
        :selected="bot.id === botStore.selectedBotId"
        @click="botStore.selectBot(bot.id)"
      />
    </div>
    <div v-if="botStore.error" class="ssp-error">{{ botStore.error }}</div>
  </div>
</template>

<script setup lang="ts">
import { useBotStore } from "../stores/useBotStore";
import BotAvatar from "./BotAvatar.vue";

const botStore = useBotStore();
withDefaults(defineProps<{ compact?: boolean }>(), { compact: true });
</script>

<style scoped>
.ssp {
  background: var(--so-panel-bg); backdrop-filter: var(--so-glass-blur);
  border: 1px solid var(--so-panel-border); border-radius: var(--so-radius-lg);
  padding: var(--so-padding);
}
.ssp--compact { padding: 8px; }
.ssp-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--so-gap-sm); }
.ssp-title { font-size: var(--so-font-size); font-weight: 700; }
.ssp-badge { font-size: var(--so-font-size-sm); padding: 2px 8px; border-radius: 10px; }
.ssp-badge--online { color: var(--so-success); background: rgba(103, 194, 58, 0.1); }
.ssp-bots { display: flex; gap: var(--so-gap-sm); flex-wrap: wrap; max-height: 200px; overflow-y: auto; }
.ssp-error { color: var(--so-danger); font-size: var(--so-font-size-sm); margin-top: var(--so-gap-sm); }
</style>
