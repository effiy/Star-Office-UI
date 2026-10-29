# Star Office UI

🌐 Language: **中文** | [English](./README.en.md) | [日本語](./README.ja.md)

## 像素办公室 × AI Agent 可视化工作台

Star Office UI 是一个像素风多 Agent 同屏可视化工作台——将 DSH Bot 团队的工作状态实时映射为像素角色动画。每个 Bot 在像素办公室中拥有独立的工位、状态指示器和角色动画。

## 快速开始

```bash
cd backend && python app.py    # 后端
cd frontend && npm run dev     # 前端 (Phaser.js + Vite)
```

## 技术栈

- **前端**: Phaser.js + Vite + TypeScript
- **后端**: Python Flask + WebSocket
- **状态同步**: bridge-state.json + HTTP API

## DSH Bot 接入

参见 [DSH Bot 接入像素办公室（一分钟）](docs/dsh-bot-quickstart.md)
