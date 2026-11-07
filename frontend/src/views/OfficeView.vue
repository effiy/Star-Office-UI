<template>
  <div class="sov">
    <!-- 🎮 Phaser rendering layer -->
    <div class="sov-canvas">
      <PhaserCanvas
        ref="phaserRef"
        :width="1280"
        :height="720"
        :auto-resize="true"
        @ready="$emit('phaser-ready', $event)"
        @error="$emit('phaser-error', $event)"
      />
    </div>

    <!-- 📐 Vue UI overlay layer -->
    <div class="sov-ui">
      <!-- Floor navigation -->
      <OfficeFloor
        :floors="botStore.floors"
        :current="botStore.currentFloor"
        :stats="botStore.floorStats"
        @switch-floor="botStore.setFloor"
      />

      <!-- Bottom panels -->
      <div class="sov-panels">
        <StatusPanel :compact="true" />
        <YesterdayMemo />
      </div>
    </div>

    <!-- 🧠 Join panel (overlay) -->
    <Transition name="panel-fade">
      <JoinPanel
        v-if="showJoinPanel"
        @close="showJoinPanel = false"
        @joined="onAgentJoined"
      />
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useBotStore } from "../stores/useBotStore";
import PhaserCanvas from "../components/PhaserCanvas.vue";
import OfficeFloor from "../components/OfficeFloor.vue";
import StatusPanel from "../components/StatusPanel.vue";
import YesterdayMemo from "../components/ui/YesterdayMemo.vue";
import JoinPanel from "../components/ui/JoinPanel.vue";
import type { SceneManagerAPI } from "../game/OfficeScene";

const botStore = useBotStore();
const phaserRef = ref<InstanceType<typeof PhaserCanvas>>();
const showJoinPanel = ref(false);

defineEmits<{
  "phaser-ready": [manager: SceneManagerAPI];
  "phaser-error": [err: Error];
}>();

function onAgentJoined() {
  showJoinPanel.value = false;
  botStore.fetchBots(); // Refresh after join
}

// Expose methods for parent
defineExpose({
  toggleJoinPanel: () => {
    showJoinPanel.value = !showJoinPanel.value;
  },
  getPhaserRef: () => phaserRef.value,
});
</script>

<style scoped>
.sov {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.sov-canvas {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.sov-ui {
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  min-height: 100%;
  pointer-events: none;
}

.sov-ui > * {
  pointer-events: auto;
}

.sov-panels {
  display: flex;
  gap: 12px;
  padding: 12px 20px;
  align-items: flex-end;
}

/* Transition */
.panel-fade-enter-active,
.panel-fade-leave-active {
  transition: opacity 0.25s ease;
}
.panel-fade-enter-from,
.panel-fade-leave-to {
  opacity: 0;
}
</style>