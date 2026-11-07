<template>
  <ErrorBoundary
    title="像素办公室启动失败"
    emoji="🏢"
    retry-label="重新加载办公室"
    hint="检查 Phaser 引擎是否正常加载。如持续失败，请联系像素办公室管理员。"
    @retry="retryBoot"
  >
    <OfficeLayout>
      <PhaserCanvas
        ref="phaserRef"
        :width="1280"
        :height="720"
        :auto-resize="true"
        @ready="onPhaserReady"
        @error="onPhaserError"
      />
      <StatusPanel />
      <OfficeFloor
        :floors="botStore.floors"
        :current="botStore.currentFloor"
        :stats="botStore.floorStats"
        @switch-floor="botStore.setFloor"
      />
    </OfficeLayout>
  </ErrorBoundary>
  <SoToast />
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from "vue";
import { useBotStore } from "./stores/useBotStore";
import { usePhaserGame } from "./composables/usePhaserGame";
import { useDSHBridge } from "./composables/useDSHBridge";
import ErrorBoundary from "./components/ErrorBoundary.vue";
import OfficeLayout from "./components/OfficeLayout.vue";
import OfficeFloor from "./components/OfficeFloor.vue";
import StatusPanel from "./components/StatusPanel.vue";
import PhaserCanvas from "./components/PhaserCanvas.vue";
import SoToast from "./components/ui/SoToast.vue";
import { useToast } from "./composables/useToast";
import type { SceneManagerAPI } from "./game/OfficeScene";

const botStore = useBotStore();
const { bridgeReady, setupBridge, teardown, stats } = usePhaserGame();
const phaserRef = ref<InstanceType<typeof PhaserCanvas>>();
const bridge = useDSHBridge();
const toast = useToast();

// ── Phaser event handlers ──

function onPhaserReady(manager: SceneManagerAPI) {
  setupBridge(manager);
  // Expose stats globally for SU-04 verification
  if (typeof window !== "undefined") {
    (window as any).__soPhaserStats = () => ({ ...stats.value });
  }
}

function onPhaserError(err: Error) {
  console.error("[App] Phaser initialization error:", err.message);
  toast.error("Phaser 引擎启动失败：" + err.message, 6000);
}

function retryBoot() {
  teardown();
  bridge.stop();
  bridge.start();
}

onMounted(() => {
  // Unified DSH bridge: loads floor registry → REST + DSH → WebSocket
  bridge.start();
});

onBeforeUnmount(() => {
  teardown();
  bridge.stop();
});
</script>