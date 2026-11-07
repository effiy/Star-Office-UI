# Star Office UI — 组件库盘点

> 生成日期：2026-11-04 | 分支：v2-dev | 框架：Vue 3 + TypeScript + Phaser 3

---

## 📦 项目架构概览

```
frontend/src/
├── components/               # 10 个 Vue 组件 + 3 个 Canvas 层
│   ├── OfficeLayout.vue      # 根布局壳
│   ├── StatusPanel.vue       # Bot 状态概览面板
│   ├── BotAvatar.vue         # Bot 头像芯片
│   ├── BotBubble.vue         # 浮动气泡弹窗
│   ├── BotInfoCard.vue       # Bot 详情卡片
│   ├── OfficeFloor.vue       # 楼层导航栏
│   ├── ErrorBoundary.vue     # 错误边界包裹器
│   ├── PhaserCanvas.vue      # Phaser 游戏生命周期管理
│   ├── ui/
│   │   ├── YesterdayMemo.vue # 昨日小记
│   │   └── JoinPanel.vue     # 加入办公室面板
│   └── canvas/               # 3 个 Phaser 渲染层 (TS)
│       ├── MapLayer.ts       # 背景/家具渲染
│       ├── CharacterLayer.ts # Agent 精灵管理
│       └── EffectLayer.ts    # 视觉特效/过渡
├── views/
│   └── OfficeView.vue        # 主视图（Vue UI + Phaser 融合）
├── stores/
│   ├── useBotStore.ts        # Bot 状态核心 Store
│   ├── office.ts             # 办公室级状态
│   └── asset.ts              # 资源加载状态
├── composables/
│   ├── usePhaserGame.ts      # Pinia↔Phaser 桥接
│   └── useDSHBridge.ts       # WebSocket/REST 数据桥接
└── game/
    ├── OfficeScene.ts        # Phaser 场景（AgentPool + 裁剪）
    ├── AgentPool.ts          # LRU Agent 渲染池（max=50）
    └── layout.ts             # 办公布局坐标定义
```

---

## 🧩 Vue 组件清单

### 1. OfficeLayout.vue — 根布局壳

**用途**：应用级布局容器，包裹 Phaser 舞台与 Vue UI 面板，管理全局 loading 态和右侧抽屉（Drawer）。

**Props**：无（纯 slot 容器）

**Slots**：
| 名称 | 说明 |
|------|------|
| `default` | 主舞台区域（PhaserCanvas） |
| `panels` | 底部面板区（StatusPanel + YesterdayMemo） |

**Emits**：无

**依赖**：
- `useBotStore` (Pinia) — `loading` / `drawerOpen` / `selectedBot`
- `StatusPanel.vue` — 右侧抽屉内的状态面板
- `BotInfoCard.vue` — 右侧抽屉内的详情卡片

**关键行为**：
- `drawerOpen` 为 true 时滑入右侧 Drawer（320px–30vw，移动端全宽）
- Loading 状态显示全屏覆盖层 + 动画进度条 (`.sol-loading`)
- `<Transition name="drawer-slide">` 驱动 Drawer 进出动画

---

### 2. StatusPanel.vue — Bot 状态概览面板

**用途**：显示当前楼层的在线 Bot 列表，每个 Bot 以 `BotAvatar` 芯片呈现；点击可选中打开详情。

**Props**：
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `compact` | `boolean` | `true` | 紧凑模式（减小 padding） |

**Emits**：无（通过 `botStore.selectBot()` 间接交互）

**依赖**：
- `useBotStore` — `onlineCount` / `botsOnCurrentFloor` / `error` / `selectedBotId` / `selectBot()`
- `BotAvatar.vue` — 传入 `bot`、`selected`，监听 `@click`

**关键行为**：
- `botsOnCurrentFloor` 是 computed — 自动过滤当前楼层
- 错误时显示 `.ssp-error`

---

### 3. BotAvatar.vue — Bot 头像芯片

**用途**：单个 Bot 的最小化表示，显示头像 emoji + 名称 + 状态指示灯。

**Props**：
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `bot` | `Bot` | (必填) | Bot 数据对象 |
| `selected` | `boolean` | `false` | 是否选中态（高亮描边） |

**Emits**：
| 名称 | 参数 | 说明 |
|------|------|------|
| `click` | — | 点击芯片时触发 |

**依赖**：
- `useBotStore` (仅类型 `Bot`)

**状态指示灯**（`.sba-dot`）：
| 状态 | 颜色 | 动画 |
|------|------|------|
| `executing` | 绿色 + 光晕 | pulse 1.6s |
| `writing` | 橙色 + 光晕 | pulse 1.2s |
| `idle` | 灰色 | 无 |
| `offline` | 空心圈 | 无 |

---

### 4. BotBubble.vue — 浮动气泡弹窗

**用途**：在 Phaser 画布层上方浮动显示 Bot 的当前状态/对话气泡。

**Props**：
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `bot` | `Bot` | (必填) | Bot 数据 |
| `visible` | `boolean` | `true` | 显示/隐藏 |
| `side` | `"left" \| "right"` | `"right"` | 气泡位置方向 |

**Emits**：
| 名称 | 参数 | 说明 |
|------|------|------|
| `close` | — | 点击关闭按钮 |

**依赖**：
- `useBotStore` (仅类型 `Bot`)

**关键行为**：
- `<Transition name="bubble-pop">` 弹入弹出动画
- `side=left` 左对齐，`side=right` 右对齐
- `position: absolute` 定位在 Phaser 画布上层

---

### 5. BotInfoCard.vue — Bot 详情卡片

**用途**：在 Drawer 中展示选中 Bot 的完整信息（头像、名称、角色、状态、详情、楼层、更新时间）。

**Props**：
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `bot` | `Bot` | (必填) | Bot 数据 |

**Emits**：
| 名称 | 参数 | 说明 |
|------|------|------|
| `close` | — | 关闭卡片 |

**状态中文映射**（computed `stateLabel`）：
| 英文状态 | 中文 |
|----------|------|
| `idle` | 空闲 |
| `writing` | 写作中 |
| `researching` | 研究中 |
| `executing` | 执行中 |
| `syncing` | 同步中 |
| `error` | 出错 |

**依赖**：
- `useBotStore` (仅类型 `Bot`)

---

### 6. OfficeFloor.vue — 楼层导航栏

**用途**：1F/2F/3F 楼层切换按钮，显示每层 "工作中/总数" 统计。

**Props**：
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `floors` | `FloorEntry[]` | (必填) | 楼层列表 `{id, label, order, yRange}` |
| `current` | `FloorId` | (必填) | 当前选中楼层 |
| `stats` | `Record<string, {total, working}>` | — | 每层统计 |

**Emits**：
| 名称 | 参数 | 说明 |
|------|------|------|
| `switch-floor` | `FloorId` | 切换楼层 |

**依赖**：
- `useBotStore` (仅类型 `FloorId`)

**关键行为**：
- `<Transition name="floor-fade" mode="out-in">` 楼层内容淡入淡出
- 移动端隐藏统计数字、缩小按钮

---

### 7. ErrorBoundary.vue — 错误边界包裹器

**用途**：Vue 3 `onErrorCaptured` 错误捕获组件，显示友好的错误界面并提供重试/重新加载。

**Props**：
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `title` | `string` | `"出了点问题"` | 自定义错误标题 |
| `emoji` | `string` | `"🦞"` | 自定义 emoji |
| `retryLabel` | `string` | `"重试"` | 重试按钮文案 |
| `showReload` | `boolean` | `true` | 是否显示重新加载按钮 |
| `hint` | `string` | — | 按钮下方提示文字 |
| `message` | `string` | — | 自定义错误信息（优先于捕获的 error.message） |

**Emits**：
| 名称 | 参数 | 说明 |
|------|------|------|
| `retry` | — | 用户点击重试 |

**Slots**：
| 名称 | 说明 |
|------|------|
| `default` | 正常时渲染的子内容 |

**Expose**：
| 名称 | 类型 | 说明 |
|------|------|------|
| `error` | `Ref<Error \| null>` | 当前错误对象 |
| `retry` | `Function` | 手动触发重试 |

**关键行为**：
- `onErrorCaptured` 捕获子组件错误，返回 `false` 阻止冒泡
- 重试：清空 error → emit `retry`
- 重新加载：`window.location.reload()`

---

### 8. PhaserCanvas.vue — Phaser 游戏生命周期管理

**用途**：SU-03 核心组件，管理 Phaser.Game 的创建/销毁、响应式缩放，并暴露 SceneManagerAPI。

**Props**：
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `width` | `number` | `1280` | 画布宽度 px |
| `height` | `number` | `720` | 画布高度 px |
| `autoResize` | `boolean` | `true` | 是否通过 ResizeObserver 自适应容器 |

**Emits**：
| 名称 | 参数 | 说明 |
|------|------|------|
| `ready` | `SceneManagerAPI` | Phaser 场景就绪 |
| `error` | `Error` | Phaser 初始化失败 |

**Expose**：
| 名称 | 类型 | 说明 |
|------|------|------|
| `getSceneManager()` | `SceneManagerAPI \| null` | 获取 Scene 管理器 |
| `getGame()` | `Phaser.Game \| null` | 获取原始 Phaser.Game 实例 |
| `resize(w, h)` | `Function` | 手动调整画布大小 |
| `forceSync()` | `Function` | 强制重新同步 agents |

**依赖**：
- `OfficeScene.ts` — `createOfficeScene()` 创建场景和管理器
- Phaser 3 (`window.Phaser`)

**关键行为**：
- `onMounted`：创建 Phaser.Game → emit `ready` → 启动 ResizeObserver
- `onBeforeUnmount`：disconnect ResizeObserver → `game.destroy(true)`
- `pixelArt: true` — 像素风格渲染
- 容器 ID 随机生成 (`phaser-canvas-xxxxxxx`)

---

### 9. YesterdayMemo.vue — 昨日小记

**用途**：从后端 `/yesterday-memo` 获取每日日记并渲染显示。

**Props**：无

**Emits**：无

**Expose**：
| 名称 | 类型 | 说明 |
|------|------|------|
| `fetchMemo` | `Function` | 手动重新获取 |

**依赖**：
- 后端 API：`GET /yesterday-memo?t={timestamp}`

**关键行为**：
- `onMounted` 时自动请求
- 四种状态：loading（脉冲点动画）→ error（显示重试按钮）→ empty（"暂无昨日日记"）→ content（v-html 渲染，`\n`→`<br>`）
- 最大高度 120px，overflow-y: auto

---

### 10. JoinPanel.vue — 加入办公室面板

**用途**：全屏遮罩弹窗，允许新 Agent 通过邀请链接或 Agent ID 加入像素办公室。

**Props**：无

**Emits**：
| 名称 | 参数 | 说明 |
|------|------|------|
| `close` | — | 关闭面板 |
| `joined` | — | 加入成功 |

**内部状态**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `agentId` | `string` | 输入的 Agent ID |
| `joinKey` | `string` | 加入密钥（可选） |
| `joining` | `boolean` | 加入中状态 |
| `error` | `string \| null` | 错误信息 |
| `copied` | `boolean` | 邀请链接复制反馈 |
| `requiresKey` | `boolean` | 是否需要密钥（通过 `/join-config` 获取） |

**依赖**：
- `GET /join-config` — 获取是否需要密钥配置
- `POST /agent-register` — 提交加入请求
- `navigator.clipboard` — 复制邀请链接

**关键行为**：
- `onMounted` 时检查 `/join-config` 决定是否显示密钥输入
- 邀请链接 = `{location.origin}/join`
- 加入成功 → emit `joined` → 父组件刷新 Bot 列表

---

## 🎨 Canvas 渲染层

### 11. MapLayer.ts — 背景/家具渲染层

**用途**：Phaser 场景的底层渲染 — 办公背景、家具精灵、动画和铭牌。

**Factory**：`createMapLayer() → MapLayerAPI`

**API**：
| 方法 | 签名 | 说明 |
|------|------|------|
| `preload` | `(scene, supportsWebP: boolean) => void` | 预加载所有图片/精灵表 |
| `create` | `(scene) => Record<string, any>` | 创建所有场景对象，返回引用 |
| `update` | `(time, delta) => void` | 帧更新（预留） |

**渲染元素**：
| 元素 | 资源 | 行为 |
|------|------|------|
| 背景 | `office_bg` | 静态图 |
| 沙发 | `sofa_busy` spritesheet | 12帧循环动画 |
| 植物 | `plants` spritesheet | 随机帧（16 种） |
| 海报 | `posters` spritesheet | 随机帧（32 种） |
| 猫 | `cats` spritesheet | 随机帧（16 种） |
| 咖啡机 | `coffee_machine` spritesheet | 95帧循环动画 |
| 服务器机房 | `serverroom` spritesheet | 动画暂停，按需启动 |
| 办公桌 | `desk_v2` 静态图 | 固定显示 |
| 花 | `flowers` spritesheet | 随机帧（16 种） |
| 铭牌 | 文本 `"像素办公室"` | 金色字体 + 棕色背景 |

**依赖**：
- `game/layout.ts` — `OFFICE_LAYOUT` 坐标配置
- 静态资源目录：`/static/`

---

### 12. CharacterLayer.ts — Agent 精灵管理层

**用途**：在 MapLayer 之上管理 Agent 角色精灵 — 同步、裁剪、气泡显示。

**Factory**：`createCharacterLayer() → CharacterLayerAPI`

**API**：
| 方法 | 签名 | 说明 |
|------|------|------|
| `init` | `(scene, pool: AgentPool) => void` | 初始化层 |
| `syncAgents` | `(bots: Bot[], currentFloor: FloorId) => void` | 同步 Bot 数据到精灵 |
| `cullOffFloor` | `(currentFloor: FloorId) => void` | 裁剪非当前楼层精灵 |
| `showBubble` | `(agentId, text, durationMs?) => void` | 显示气泡（默认 3s） |

**核心逻辑**：
- 楼层区域映射：1F(y:40–240)、2F(y:260–480)、3F(y:500–696)
- `agentZones` Map 记录每个 Agent 的 `(zoneIndex, index)` 分配
- `computeStableAgentPosition()` 为每个 zone 的 Agent 计算稳定坐标
- 裁剪：±60px margin 外的精灵被 `pool.release()`
- 气泡：白色矩形 + 黑色描边 + 居中文本，3s 自动销毁（z-depth: 9999）

**依赖**：
- `game/AgentPool.ts` — AgentPool（LRU 50）
- `game/layout.ts` — `computeStableAgentPosition` / `AGENT_ZONES`
- `useBotStore.ts` — `Bot` / `FloorId` / `FLOOR_CONFIG`

---

### 13. EffectLayer.ts — 视觉特效层

**用途**：Phaser 最上层 — 粒子特效、楼层过渡动画、错误/同步指示。

**Factory**：`createEffectLayer() → EffectLayerAPI`

**API**：
| 方法 | 签名 | 说明 |
|------|------|------|
| `init` | `(scene) => void` | 初始化 |
| `playFloorTransition` | `(from, to) => void` | 楼层切换遮罩过渡 |
| `showErrorGlow` | `(x, y) => void` | 红色错误光晕（800ms 扩散淡出） |
| `showSyncParticles` | `(x, y) => void` | 绿色同步粒子（4 点旋转扩散） |
| `update` | `(time, delta) => void` | 帧更新（预留） |
| `clear` | `() => void` | 清除所有活跃特效 |

**特效详解**：
| 特效 | 实现 | 参数 |
|------|------|------|
| 楼层过渡 | 黑色矩形 alpha 0→0.3→0，yoyo 150ms | depth 5000 |
| 错误光晕 | 红色半透明圆，scale 1→1.5，alpha 0.15→0 | depth 4900, 800ms |
| 同步粒子 | 4 个绿色圆点环形排列，alpha 0.6→0，scale 1→0.1 | depth 4900, 1200ms |

**依赖**：
- Phaser Tweens（优先） / requestAnimationFrame（降级）

---

## 🗄️ Pinia Store 清单

### useBotStore (`stores/useBotStore.ts`)

**职责**：全局 Bot 状态管理 — 数据获取、WebSocket 实时更新、楼层管理、UI 状态。

**State**：`bots` / `currentFloor` / `selectedBotId` / `loading` / `error` / `drawerOpen` / `isAnimating` / `wsConnected` / `lastSnapshot`

**Getters**：`floors` / `botsOnCurrentFloor` / `selectedBot` / `onlineCount` / `workingCount` / `floorStats`

**Actions**：
- `fetchBots()` — REST 全量拉取 (`GET /agents`)
- `fetchFloor(floor)` — 按楼层拉取 (`GET /office/floor/{n}`)
- `setFloor(floor)` — 切换楼层（350ms 动画锁）
- `selectBot(id)` / `closeDrawer()` — 选中/关闭抽屉
- `connectWebSocket()` / `disconnectWebSocket()` — WebSocket 管理（`:19002`，5s 重连）
- `ingestSnapshot()` / `ingestChanges()` — 处理 WS 消息

**楼层分配**：32 个已知 Bot 硬编码 + 其余 hash 兜底 → 上限 50

---

### useOfficeStore (`stores/office.ts`)

**职责**：办公室级配置 — 区域映射、资源坐标、运行时配置。

**State**：`currentFloor` / `assetPositions` / `assetDefaults` / `runtimeConfig`

**区域映射** (`AREA_MAP`)：breakroom/writing/researching/error/syncing → 坐标+图标

---

### useAssetStore (`stores/asset.ts`)

**职责**：游戏资源加载状态追踪 — 图片/精灵表/字体/音频。

**State**：`assets` (Map) / `loading` / `totalCount` / `loadedCount` / `error`

**Getters**：`progress` (0–100) / `isReady` / `failedAssets`

---

## 🔗 Composable 清单

### usePhaserGame — Pinia↔Phaser 桥接

**职责**：双向数据流 — Pinia store 变更 → 16ms 防抖 → Phaser syncAgents()。

**用法**：`<PhaserCanvas @ready="setupBridge" />`

**返回值**：`bridgeReady` / `stats` / `setupBridge()` / `teardown()` / `getManager()` / `forceSync()`

---

### useDSHBridge — WebSocket/REST 数据桥接

**职责**：双通道数据获取 — WebSocket 主通道 + REST 3s 轮询降级。

**用法**：组件 `onMounted` → `start()` → 双通道自动切换

---

## 📊 组件依赖关系图

```
App.vue
└── OfficeLayout.vue                          ← 根布局壳
    ├── [slot] OfficeView.vue                  ← 主视图
    │   ├── PhaserCanvas.vue                   ← Phaser 游戏容器
    │   │   └── OfficeScene.ts                 ← 场景引擎
    │   │       ├── MapLayer.ts                ← 背景层
    │   │       ├── CharacterLayer.ts          ← 角色层
    │   │       │   └── AgentPool.ts (LRU 50)  ← 渲染池
    │   │       └── EffectLayer.ts             ← 特效层
    │   ├── OfficeFloor.vue                    ← 楼层导航
    │   ├── StatusPanel.vue                    ← 状态面板
    │   │   └── BotAvatar.vue (×N)             ← Bot 芯片
    │   ├── YesterdayMemo.vue                  ← 昨日小记
    │   └── JoinPanel.vue (条件渲染)           ← 加入面板
    ├── [slot panels] StatusPanel.vue          ← 底部面板
    ├── [drawer] StatusPanel.vue               ← Drawer 中
    └── [drawer] BotInfoCard.vue               ← 详情卡片

Data Flow:
  useDSHBridge → useBotStore ← usePhaserGame → PhaserCanvas → SceneManagerAPI
                     ↕                           ↕
              (所有 Vue 组件)              (Map/Character/Effect Layers)
```

---

## 🎯 设计规范总结

| 设计令牌 | CSS 变量 | 用途 |
|----------|----------|------|
| 主背景 | `--so-bg` | 页面底色 |
| 面板背景 | `--so-panel-bg` | 卡片/面板底 |
| 玻璃背景 | `--so-glass-bg` | 半透明背景 |
| 玻璃模糊 | `--so-glass-blur` | backdrop-filter |
| 面板边框 | `--so-panel-border` | 边框色 |
| 主文字 | `--so-ink` | 主要文字色 |
| 次要文字 | `--so-ink-muted` | 辅助文字 |
| 弱化文字 | `--so-ink-dim` | 极淡文字 |
| 强调色 | `--so-accent` | 交互高亮 |
| 成功色 | `--so-success` | executing 状态 |
| 警告色 | `--so-warning` | writing 状态 |
| 危险色 | `--so-danger` | 错误状态 |
| 像素字体 | `--so-font-pixel` | ArkPixel, monospace |
| 过渡 | `--so-transition` | 统一过渡参数 |
| 圆角 | `--so-radius` / `--so-radius-lg` | 组件圆角 |

---

## 📋 待完善项

- [ ] 建立 Storybook / Histoire 组件展示
- [ ] 为每个 Vue 组件编写单元测试 (Vitest)
- [ ] BotBubble 目前未被 Vue UI 层使用（仅在 Phaser CharacterLayer 中有独立实现）
- [ ] 统一 Z-Index 层级管理（当前散落在各组件中）
- [ ] 移动端响应式覆盖不完整（仅 OfficeFloor 有 `@media`）
- [ ] ErrorBoundary 可扩展为全局错误上报

---

> 总计：**10 个 Vue 组件** + **3 个 Canvas TypeScript 层** + **3 个 Pinia Store** + **2 个 Composable** + **1 个 View** = **19 个前端模块**