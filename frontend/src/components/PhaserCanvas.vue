<template>
  <div
    ref="containerRef"
    :id="containerId"
    class="phaser-canvas"
  />
</template>

<script setup lang="ts">
/**
 * PhaserCanvas.vue — SU-03 core component
 *
 * Manages Phaser.Game lifecycle within Vue 3:
 * - Creates Phaser game on mount, destroys on unmount
 * - Embeds OfficeScene (Pool + Culling from SU-04)
 * - Handles responsive resize via ResizeObserver
 * - Exposes SceneManagerAPI for Pinia bridge
 */

import { ref, onMounted, onBeforeUnmount } from "vue";
import { createOfficeScene, type SceneManagerAPI } from "../game/OfficeScene";

// ═══ Props ═══

const props = withDefaults(
  defineProps<{
    /** Canvas width in px (default: game's native 1280, CSS-scaled by container) */
    width?: number;
    /** Canvas height in px */
    height?: number;
    /** Whether to auto-resize when container changes */
    autoResize?: boolean;
  }>(),
  { width: 1280, height: 720, autoResize: true }
);

// ═══ Emits ═══

const emit = defineEmits<{
  ready: [manager: SceneManagerAPI];
  error: [err: Error];
}>();

// ═══ Refs ═══

const containerId = `phaser-canvas-${Math.random().toString(36).slice(2, 9)}`;
const containerRef = ref<HTMLElement>();



// ═══ Phaser lifecycle ═══

let game: Phaser.Game | null = null;
let sceneManager: SceneManagerAPI | null = null;
let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  if (!containerRef.value) {
    emit("error", new Error("PhaserCanvas: container not mounted"));
    return;
  }

  try {
    const { sceneConfig, getManager } = createOfficeScene();

    game = new Phaser.Game({
      type: (window as any).Phaser?.AUTO ?? 0,
      width: props.width,
      height: props.height,
      parent: containerId,
      pixelArt: true,
      backgroundColor: "#1a1a2e",
      physics: {
        default: "arcade",
        arcade: { gravity: { y: 0 }, debug: false },
      },
      scale: {
        mode: (window as any).Phaser?.Scale?.FIT ?? 1,
        autoCenter: (window as any).Phaser?.Scale?.CENTER_BOTH ?? 1,
      },
      scene: sceneConfig,
    });

    sceneManager = getManager();
    if (sceneManager) {
      emit("ready", sceneManager);
    }

    // Resize observer
    if (props.autoResize) {
      resizeObserver = new ResizeObserver(() => {
        if (containerRef.value && game) {
          const w = containerRef.value.clientWidth;
          const h = containerRef.value.clientHeight;
          if (w > 0 && h > 0) {
            try {
              game.scale.resize(w, h);
            } catch { /* ignore resize errors */ }
          }
        }
      });
      resizeObserver.observe(containerRef.value);
    }
  } catch (err) {
    emit("error", err instanceof Error ? err : new Error(String(err)));
  }
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  resizeObserver = null;

  if (game) {
    game.destroy(true);
    game = null;
  }
  sceneManager = null;
});

// ═══ Public API (exposed to parent) ═══

defineExpose({
  /** Get the SceneManager for Pinia bridge access */
  getSceneManager: (): SceneManagerAPI | null => sceneManager,
  /** Get the raw Phaser.Game instance */
  getGame: (): Phaser.Game | null => game,
  /** Manually resize the canvas */
  resize: (width: number, height: number) => {
    if (game) {
      game.scale.resize(width, height);
    }
  },
  /** Force re-sync agents (useful after store updates) */
  forceSync: () => sceneManager?.syncAgents([]),
});
</script>

<style scoped>
.phaser-canvas {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
  background: var(--so-dark-bg, #1a1a2e);
}

/* Phaser inserts its own <canvas> as a child — make it fill */
.phaser-canvas :deep(canvas) {
  display: block;
  max-width: 100%;
  height: auto;
}
</style>