<template>
  <ErrorBoundary
    title="像素办公室启动失败"
    emoji="🏢"
    retry-label="重新加载办公室"
    hint="检查 Phaser 引擎是否正常加载。如持续失败，请联系像素办公室管理员。"
    @retry="retryBoot"
  >
    <OfficeLayout>
      <div id="game-container" ref="gameContainer" />
      <StatusPanel />
      <OfficeFloor
        :floors="botStore.floors"
        :current="botStore.currentFloor"
        :stats="botStore.floorStats"
        @switch-floor="botStore.setFloor"
      />
    </OfficeLayout>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from "vue";
import { useBotStore } from "./stores/useBotStore";
import { usePhaserGame } from "./composables/usePhaserGame";
import ErrorBoundary from "./components/ErrorBoundary.vue";
import OfficeLayout from "./components/OfficeLayout.vue";
import OfficeFloor from "./components/OfficeFloor.vue";
import StatusPanel from "./components/StatusPanel.vue";

const botStore = useBotStore();
const gameContainer = ref<HTMLElement>();

async function boot() {
  await botStore.fetchBots();
  botStore.connectWebSocket();
  if (gameContainer.value) {
    usePhaserGame(gameContainer);
  }
}

function retryBoot() {
  boot();
}

onMounted(() => { boot(); });
onBeforeUnmount(() => { botStore.disconnectWebSocket(); });
</script>