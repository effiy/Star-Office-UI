<template>
  <nav class="sof">
    <button
      v-for="f in floors"
      :key="f.id"
      class="sof-btn"
      :class="{ 'is-active': f.id === current }"
      @click="$emit('switch-floor', f.id)"
    >
      <span class="sof-btn__label">{{ f.label }}</span>
      <span v-if="stats?.[f.id]" class="sof-btn__count">
        {{ stats[f.id].working }}/{{ stats[f.id].total }}
      </span>
    </button>
  </nav>
  <Transition name="floor-fade" mode="out-in">
    <div :key="current" class="sof-content">
      <slot />
    </div>
  </Transition>
</template>

<script setup lang="ts">
import type { FloorId } from "../stores/useBotStore";

interface FloorEntry {
  id: FloorId;
  label: string;
  order: number;
  yRange: readonly [number, number];
}

defineProps<{
  floors: FloorEntry[];
  current: FloorId;
  stats?: Record<string, { total: number; working: number }>;
}>();

defineEmits<{
  "switch-floor": [floor: FloorId];
}>();
</script>

<style scoped>
.sof { display: flex; gap: var(--so-gap-sm); padding: 8px var(--so-padding-lg); justify-content: center; flex-shrink: 0; }
.sof-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; font-family: var(--so-font-pixel); font-size: var(--so-font-size-sm);
  color: var(--so-ink-muted); background: var(--so-glass-bg);
  border: 1px solid var(--so-panel-border); border-radius: var(--so-radius);
  cursor: pointer; transition: all var(--so-transition);
}
.sof-btn:hover { color: var(--so-ink); border-color: var(--so-accent); }
.sof-btn.is-active { color: var(--so-ink); background: var(--so-accent); font-weight: 700; }
.sof-btn__label { white-space: nowrap; }
.sof-btn__count { font-size: 10px; opacity: 0.6; font-variant-numeric: tabular-nums; }
.sof-content { flex: 1; min-height: 0; position: relative; }
.floor-fade-enter-active, .floor-fade-leave-active { transition: opacity 0.3s ease; }
.floor-fade-enter-from, .floor-fade-leave-to { opacity: 0; }

@media (max-width: 600px) {
  .sof { gap: 4px; padding: 6px; overflow-x: auto; }
  .sof-btn { padding: 4px 10px; font-size: 10px; white-space: nowrap; }
  .sof-btn__count { display: none; }
}
</style>