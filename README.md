# Star-Office-UI v2 架构

> 🏗️ v2 目标架构 · Vue 3 + Phaser + Pinia + 3 层布局 + DSH 深度集成

🌐 [中文](./README.md) | [English](./README.en.md) | [日本語](./README.ja.md)

```
┌──────────────────────────────────────────────────┐
│                  🏢 pixel office                  │
│                                                  │
│  📐 UI 层 (Vue 3)    │  🎮 渲染层 (Phaser)      │
│  ┌────────────────┐  │  ┌──────────────────┐    │
│  │ AgentList      │  │  │ MapLayer         │    │
│  │ StatusBubble   │  │  │ CharacterLayer   │    │
│  │ YesterdayMemo  │  │  │ EffectLayer      │    │
│  │ DrawerPanel    │  │  └──────────────────┘    │
│  └────────────────┘  │                          │
│                      │  🔌 DSH Bridge           │
│  🧠 状态层 (Pinia)   │  ┌──────────────────┐    │
│  ┌────────────────┐  │  │ ds_bot_watcher   │    │
│  │ useAgentStore  │  │  │ (:19001 bridge)  │    │
│  │ useOfficeStore │  │  │ (:19002 api)     │    │
│  │ useAssetStore  │──┼──│ (:19000 board)   │    │
│  └────────────────┘  │  └──────────────────┘    │
└──────────────────────────────────────────────────┘
```

## 🚀 快速体验

```bash
git clone https://github.com/ringhyacinth/Star-Office-UI.git && cd Star-Office-UI
pnpm install && pnpm dev
# → http://127.0.0.1:19000
```

| 端口 | 服务 | 说明 |
|:---:|------|------|
| `19000` | 🏠 看板 | Vue 3 + Phaser 像素办公室 |
| `19001` | 🔌 Bridge | DSH Bot 状态桥接 |
| `19002` | 📡 API | `/ds-bot-states` 查询 |

## 🏗️ 三层布局

```
┌────────────────────────────────────────┐
│  📐 UI 层 (Vue 3 DOM)                  │
│  AgentList · StatusBubble · Drawer     │
│  YesterdayMemo · JoinPanel             │
├────────────────────────────────────────┤
│  🎮 渲染层 (Phaser Canvas)              │
│  MapLayer · CharacterLayer · FXLayer   │
├────────────────────────────────────────┤
│  🧠 状态层 (Pinia → Flask API)         │
│  3s 轮询 · 增量更新 · DSH 桥接          │
└────────────────────────────────────────┘
```

## ⚙️ 技术栈

| 层 | v1 (当前) | v2 (目标) |
|----|----------|----------|
| UI | 原生 HTML/JS (4900行) | Vue 3 + TypeScript + Vite |
| 状态 | 全局变量 + localStorage | Pinia stores + 持久化 |
| 渲染 | Phaser.js | Phaser.js (保留) |
| 后端 | Python Flask | Python Flask (保留) |
| DSH 集成 | ds_bot_watcher.py | watcher + Pinia 双向绑定 |

## 📡 API

| 端点 | 端口 | 说明 |
|------|:---:|------|
| `GET /ds-bot-states` | 19002 | DSH Bot 状态列表 |
| `GET /office/floor/{n}` | 19000 | 楼层 n 的办公室视图 |
| `POST /agent-push` | 19000 | Agent 推送状态 |

详见 [API 参考](./docs/api-reference.md)

## 🔌 DSH 集成

```
DSH inflight.json → watcher (:19001) → Pinia → Phaser 动画
                    ↑ Bot 手动 curl 也可推送
```

[📖 一分钟接入](./docs/dsh-bot-quickstart.md) · [📖 v2 迁移指南](./docs/v2-migration-guide.md)

---

📄 许可：MIT（代码）| 像素美术：LimeZu（学习/演示）