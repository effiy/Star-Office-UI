# Star-Office-UI v2 迁移指南

> 📐 从 v1（4900 行单文件 HTML）到 v2（Vue 3 组件 + Pinia 状态）

## 📊 变化一览

| 维度 | v1 | v2 |
|------|----|----|
| 🧩 UI | 4900 行 `index.html` | ~20 个 `.vue` SFC |
| 🧠 状态 | `window.__state` + localStorage | Pinia stores |
| 🏗️ 布局 | 单层 canvas | 📐 UI 层 + 🎮 渲染层 + 🧠 状态层 |
| 🔌 DSH | curl 推送 | `ds_bot_watcher` 自动 + Pinia 双向 |
| ⚡ 启动 | `python3 app.py` | `pnpm dev` (Vite HMR) |
| 📦 构建 | 无 | `pnpm build` → `dist/` |

## 🗺️ 组件拆分

```
v1: index.html (4900行)
    │
    ▼
v2: src/
    ├── App.vue                    # 根组件——3 层布局容器
    ├── views/
    │   └── OfficeView.vue         # 办公室主视图
    ├── components/
    │   ├── canvas/                # 🎮 Phaser 渲染层
    │   │   ├── GameCanvas.vue     #   Phaser 挂载点
    │   │   ├── MapLayer.ts        #   地图层——Tiled + AI 背景
    │   │   ├── CharacterLayer.ts  #   角色层——spritesheet 动画
    │   │   └── EffectLayer.ts     #   特效层——粒子/雨天/夜间
    │   └── ui/                    # 📐 Vue UI 层
    │       ├── AgentList.vue      #   Agent 列表
    │       ├── StatusBubble.vue   #   状态气泡
    │       ├── YesterdayMemo.vue  #   昨日小记
    │       ├── JoinPanel.vue      #   加入办公室
    │       └── DrawerPanel.vue    #   侧边栏
    ├── stores/                    # 🧠 Pinia 状态
    │   ├── agent.ts               #   Agent 状态——idle/executing/...
    │   ├── office.ts              #   办公室——楼层/区域/布局
    │   └── asset.ts               #   资产——角色/场景/装饰
    └── composables/               # 🔧 逻辑复用
        ├── useDSHBridge.ts        #   DSH 桥接——轮询+推送
        └── usePhaser.ts           #   Phaser 生命周期
```

## 📋 迁移步骤

### 1️⃣ 项目初始化

```bash
pnpm create vite star-office-ui --template vue-ts
pnpm add vue-router pinia phaser
pnpm add -D @types/node
```

### 2️⃣ Phaser → Vue 桥接

```ts
// composables/usePhaser.ts
export function usePhaser(container: Ref<HTMLElement>) {
  const game = ref<Phaser.Game>()
  
  onMounted(() => {
    game.value = new Phaser.Game({
      type: Phaser.AUTO,
      parent: container.value,
      scene: [OfficeScene]
    })
  })
  
  onUnmounted(() => game.value?.destroy(true))
  return { game }
}
```

### 3️⃣ `window.__state` → Pinia

```
v1:  window.__state = { agents: [...], ... }
         │  全局可变，调试困难
         ▼
v2:  const store = useAgentStore()
     store.agents  // reactive + typed + devtools
```

### 4️⃣ `setInterval` → `useDSHBridge`

```ts
// composables/useDSHBridge.ts
export function useDSHBridge() {
  const store = useAgentStore()
  
  // 每 3 秒轮询 DSH bridge
  useIntervalFn(async () => {
    const bots = await fetch('/ds-bot-states').then(r => r.json())
    store.syncFromDSH(bots.bots)
  }, 3000)
}
```

### 5️⃣ HTML 模板 → Vue SFC

```
v1 <div id="agent-list">          →  <AgentList />
v1 <div id="status-bubble">       →  <StatusBubble />
v1 <div id="yesterday-memo">      →  <YesterdayMemo />
v1 <div id="join-panel">          →  <JoinPanel />
```

## ⚠️ 保留不变

| 模块 | 原因 |
|------|------|
| Phaser.js | 像素渲染引擎——无替代方案 |
| Python Flask 后端 | API 稳定，无需重写 |
| `ds_bot_watcher.py` | DSH 集成已验证 |
| 像素美术资产 | LimeZu spritesheet——直接复用 |
| `state.json` / `agents-state.json` | 数据格式不变 |

## 🔑 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 构建工具 | Vite | HMR 快 10×，原生 ESM |
| 状态管理 | Pinia | Vue 3 官方推荐，devtools 支持 |
| Phaser 集成 | Composables | 生命周期绑定，避免内存泄漏 |
| 组件通信 | Pinia + props | 单向数据流，可追踪 |
| DSH 桥接 | Composable | 自动清理，可测试 |

## 🧪 验证清单

- [ ] `pnpm dev` → :19000 加载成功
- [ ] 16 个 DSH Bot 状态同步正常
- [ ] Phaser 60fps 同屏渲染
- [ ] 中/英/日 三语切换
- [ ] 移动端自适应
- [ ] `pnpm build` 产物 < 2MB (gzip)
- [ ] 兼容现有 `ds_bot_watcher.py`