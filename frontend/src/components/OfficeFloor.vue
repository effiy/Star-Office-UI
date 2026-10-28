<template>
  <nav class="sof">
    <button
      v-for="floor in floors"
      :key="floor"
      class="sof-btn"
      :class="{ 'is-active': floor === current }"
      @click="$emit('switch-floor', floor)"
    >
      {{ floor }}
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

defineProps<{
  floors: readonly FloorId[];
  current: FloorId;
}>();

defineEmits<{
  "switch-floor": [floor: FloorId];
}>();
</script>

<style scoped>
.sof { display: flex; gap: var(--so-gap-sm); padding: var(--so-padding) var(--so-padding-lg); justify-content: center; flex-shrink: 0; }
.sof-btn {
  padding: 6px 16px; font-family: var(--so-font-pixel); font-size: var(--so-font-size-sm);
  color: var(--so-ink-muted); background: var(--so-glass-bg);
  border: 1px solid var(--so-panel-border); border-radius: var(--so-radius);
  cursor: pointer; transition: all var(--so-transition);
}
.sof-btn:hover { color: var(--so-ink); border-color: var(--so-accent); }
.sof-btn.is-active { color: var(--so-ink); background: var(--so-accent); font-weight: 700; }
.sof-content { flex: 1; min-height: 0; position: relative; }
.floor-fade-enter-active, .floor-fade-leave-active { transition: opacity 0.3s ease; }
.floor-fade-enter-from, .floor-fade-leave-to { opacity: 0; }

@media (max-width: 600px) {
  .sof { gap: 4px; padding: 8px; overflow-x: auto; }
  .sof-btn { padding: 4px 10px; font-size: 10px; white-space: nowrap; }
}
</style>
