<template>
  <div v-if="error" class="sbe">
    <div class="sbe-card">
      <span class="sbe-emoji">{{ emoji }}</span>
      <h2 class="sbe-title">{{ title }}</h2>
      <p class="sbe-detail">{{ error.message || String(error) }}</p>
      <div class="sbe-actions">
        <button class="sbe-btn sbe-btn--primary" @click="retry">
          🔄 {{ retryLabel }}
        </button>
        <button v-if="showReload" class="sbe-btn" @click="reload">
          🔁 重新加载
        </button>
      </div>
      <p v-if="hint" class="sbe-hint">{{ hint }}</p>
    </div>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { ref, onErrorCaptured, computed } from "vue";

interface Props {
  /** Custom error title. Default: "出了点问题" */
  title?: string;
  /** Custom emoji. Default: "🦞" (shrimp — 虾头梗) */
  emoji?: string;
  /** Custom retry button label */
  retryLabel?: string;
  /** Show reload button */
  showReload?: boolean;
  /** Optional hint text below the buttons */
  hint?: string;
  /** Custom error message for specific scenarios */
  message?: string;
}

const props = withDefaults(defineProps<Props>(), {
  title: "出了点问题",
  emoji: "🦞",
  retryLabel: "重试",
  showReload: true,
});

const emit = defineEmits<{ retry: [] }>();

const error = ref<Error | null>(null);
const displayMessage = computed(() => props.message || error.value?.message || "");

onErrorCaptured((err: Error) => {
  error.value = err;
  console.warn("[ErrorBoundary] Caught:", err.message);
  return false; // prevent propagation
});

function retry() {
  error.value = null;
  emit("retry");
}

function reload() {
  window.location.reload();
}

defineExpose({ error, retry });
</script>

<style scoped>
.sbe {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 40px 20px;
  background: var(--so-bg);
  font-family: var(--so-font-pixel);
}
.sbe-card {
  text-align: center;
  max-width: 420px;
  padding: 40px 32px;
  background: var(--so-panel-bg);
  backdrop-filter: var(--so-glass-blur);
  border: 1px solid var(--so-panel-border);
  border-radius: var(--so-radius-lg);
  box-shadow: var(--so-shadow-lg);
}
.sbe-emoji { font-size: 48px; display: block; margin-bottom: 12px; }
.sbe-title { font-size: var(--so-font-size-xl); font-weight: 700; color: var(--so-ink); margin: 0 0 8px; }
.sbe-detail { font-size: var(--so-font-size-sm); color: var(--so-ink-muted); line-height: 1.5; margin: 0 0 20px; word-break: break-word; }
.sbe-actions { display: flex; gap: var(--so-gap-sm); justify-content: center; flex-wrap: wrap; }
.sbe-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 20px; font-family: var(--so-font-pixel); font-size: var(--so-font-size);
  border: 1px solid var(--so-panel-border); border-radius: var(--so-radius);
  background: var(--so-glass-bg); color: var(--so-ink-muted);
  cursor: pointer; transition: all var(--so-transition);
}
.sbe-btn:hover { border-color: var(--so-accent); color: var(--so-ink); }
.sbe-btn--primary {
  background: var(--so-ink); color: var(--so-bg); border-color: var(--so-ink);
}
.sbe-btn--primary:hover { opacity: 0.85; }
.sbe-hint { font-size: 10px; color: var(--so-ink-dim); margin-top: 16px; }
</style>