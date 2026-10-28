# DSH Bot 接入像素办公室（一分钟）

> 让 DSH Bot 的工作状态实时显示在像素办公室看板上。

## 前置条件

- Star-Office-UI 已部署并运行
  - 看板：`http://127.0.0.1:19000`
  - 桥接：`http://127.0.0.1:19001`
  - DSH Bot API：`http://127.0.0.1:19002`

## 一分钟接入

### 第 1 步：Bot 开始工作时推送

```bash
curl -s -X POST http://127.0.0.1:19001/state \
  -H "Content-Type: application/json" \
  -d '{"bot":"你的Bot名","state":"executing"}'
```

### 第 2 步：工作结束时置为空闲

```bash
curl -s -X POST http://127.0.0.1:19001/state \
  -H "Content-Type: application/json" \
  -d '{"bot":"你的Bot名","state":"idle"}'
```

### 第 3 步：验证

```bash
# 查看所有 Bot 状态
curl http://127.0.0.1:19002/ds-bot-states

# 只看工作中的 Bot
curl http://127.0.0.1:19002/ds-bot-states?state=executing
```

打开 `http://127.0.0.1:19000` 查看像素办公室，Bot 的像素角色应出现在对应区域。

---

## 在 Bot 配置中固化

在 Bot 的 `CLAUDE.md` 或 `AGENTS.md` 中添加：

```markdown
## pixel office 状态同步
- 开始工作前：curl -s -X POST http://127.0.0.1:19001/state -H "Content-Type: application/json" -d '{"bot":"BOT名称","state":"executing"}'
- 工作结束后：curl -s -X POST http://127.0.0.1:19001/state -H "Content-Type: application/json" -d '{"bot":"BOT名称","state":"idle"}'
- 遇到错误时：curl -s -X POST http://127.0.0.1:19001/state -H "Content-Type: application/json" -d '{"bot":"BOT名称","state":"error"}'
```

---

## Bot 名称映射

| DSH Bot | 名称参数 | 像素角色 |
|---------|---------|---------|
| Chief | `"Chief"` | 👑 骑士 |
| Git管家 | `"Git管家"` | 🐙 章鱼 |
| Readme管家 | `"Readme管家"` | 📝 文书 |
| 知识管理者 | `"知识管理者"` | 📚 智者 |
| 软件工程师 | `"软件工程师"` | 💻 开发者 |
| AI工程师 | `"AI工程师"` | 🤖 AI |
| SRE工程师 | `"SRE工程师"` | 🔧 运维 |
| 产品经理 | `"产品经理"` | 📋 PM |
| 像素办公室 | `"像素办公室"` | 🏢 办公室 |

---

## 状态说明

| state | 办公室区域 | 像素动画 | 何时使用 |
|-------|-----------|---------|---------|
| `idle` | 🛋 休息区 | 呼吸动画 | 待命中 / 任务完成 |
| `executing` | 💻 工作区 | 工具动画 | 正在执行任务 |
| `writing` | 💻 工作区 | 打字动画 | 写代码/文档 |
| `researching` | 💻 工作区 | 搜索动画 | 搜索/调研 |
| `syncing` | 💻 工作区 | 同步动画 | 同步数据 |
| `error` | 🐛 Bug 区 | 红色抖动 | 报错/异常 |

---

## Join Key 多 Agent 协作

多个 Bot 通过同一个 join key 加入共享办公室：

```bash
# Bot 加入共享办公室
curl -s -X POST http://127.0.0.1:19001/join-agent \
  -H "Content-Type: application/json" \
  -d '{"name":"Git管家","key":"daily-standup-room"}'

# 其他 Bot 用同一个 key 加入
curl -s -X POST http://127.0.0.1:19001/join-agent \
  -H "Content-Type: application/json" \
  -d '{"name":"Readme管家","key":"daily-standup-room"}'
```

---

## 自动监控（ds_bot_watcher）

部署 `ds_bot_watcher.py` 后无需手动推送：

```bash
cd /Users/yi/YrY/Star-Office-UI
python3 ds_bot_watcher.py &
```

watcher 自动读取 `~/.dsh/bot/inflight.json`，检测 Bot turn 状态变化 → 立即推送到 sync-bridge。

---

## API 速查

| 端点 | 用途 |
|------|------|
| `POST :19001/state` | Bot 推送状态 |
| `GET :19001/state` | 获取所有 Bot 状态 |
| `GET :19002/ds-bot-states` | DSH Bot 状态摘要 |
| `GET :19000/` | 像素办公室看板 |
| `GET :19000/status` | 主 Agent 状态 |

---

## 故障排查

| 症状 | 检查 |
|------|------|
| Bot 不显示 | `curl :19002/ds-bot-states` 确认状态已推送 |
| 状态不更新 | `ps aux \| grep ds_bot_watcher` 确认进程运行 |
| pixel office 打不开 | `curl :19000/health` 确认后端存活 |
| API 返回空 | 检查 `agents-state.json` 是否被写入 |
| watcher 404 | sync-bridge 是否已启动（:19001） |