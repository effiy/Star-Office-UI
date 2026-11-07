# ADR-001: DSH 数据直连与单一真相源架构

- 状态：已接受
- 日期：2026-11-07
- 决策人：技术管家·哲思（TL）
- 关联：SU-01/02/03/04 交付后架构审计（SU·架构·筑桥）

## 1. 问题陈述

Star-Office-UI 当前数据链路存在三处断点：
1. `useDSHBridge.ts` 已实现（WS 主 + REST 备）但 App.vue 未调用——手写 `fetchBots + connectWebSocket`，双源逻辑死而不活
2. `dsh_server.py :19003` 仍是旧技术栈，与 SU-02 后的 FastAPI 主体不一致
3. `useBotStore.ts` 的 `BOT_HOME_FLOOR` 硬编码 50 条目——新增 Bot 需改源码，与 `floor-registry.json` 单一真相源原则冲突

用户要求：**数据打通 YiAi ↔ DSH，需要更专业。**

## 2. 决策上下文

- SU-01~04 已全部交付并验收（ws_server 压测 2-3ms、45 路由零 Flask、26 前端文件、50 agent 容量）
- 现有链路：DSH Bot → dsh_server :19003 → ws_server :19002 → WebSocket → useBotStore → Phaser
- `/ds-bot-states` 端点已就绪但前端未消费——DSH 权威数据未直接进入 store
- AI专家·铁甲 正在调研 YiAi 接入面

## 3. 决策

1. **DSH 为 Bot 状态唯一权威源**：前端经 `useDSHBridge` 统一收口，WS(:19002) 主路径 + REST `/ds-bot-states` 备路径，双源合并去重后写入 `useBotStore`
2. **dsh_server 迁移 FastAPI**：与 SU-02 技术栈统一
3. **楼层分配动态化**：`BOT_HOME_FLOOR` 硬编码 → 运行时从 `/floor-registry.json` 加载，hash 兜底不变
4. **YiAi 接入**：等铁甲调研报告，按同一数据契约（Bot 状态 schema）扩展，不另起炉灶

## 4. 决策理由

- 单一真相源（SSOT）消除 ws_server 中转与 DSH 权威数据的状态漂移
- 双源并行提升可用性：WS 断连时 REST 自动兜底（已有 6 故障场景文档）
- FastAPI 统一降低维护认知成本，复用 SU-02 的中间件与降级模式
- 动态注册实现「新 Bot 零代码改动」——与 SU-04 扩容路径闭环

## 5. 权衡分析

| 收益 | 成本 |
|------|------|
| 数据一致性 ↑ | 双源合并需去重逻辑（timestamp 比较） |
| 扩容零改码 | floor-registry.json 成为运行时依赖（需 404 兜底） |
| 技术栈统一 | dsh_server 迁移需回归测试（:19003 契约不变） |

## 6. 替代方案

- **前端直连 DSH API**：否决——跨域/鉴权复杂度，且丢失 ws_server 的聚合能力
- **维持 Flask dsh_server**：否决——技术栈分裂，长期维护成本更高
- **YiAi 独立数据通道**：否决——违反 SSOT，先调研后按统一契约接入

## 7. 实施计划

| 任务 | 负责 | 范围 |
|------|------|------|
| useDSHBridge 接入 App.vue + `/ds-bot-states` 消费 | SU·架构·筑桥 | 仅前端 |
| BOT_HOME_FLOOR 动态加载 | SU·架构·筑桥 | useBotStore.ts |
| dsh_server.py → FastAPI | SU·后端·铸舰 | 仅 :19003，契约不变 |
| YiAi 接入面调研 + 数据契约扩展 | AI专家·铁甲 | 调研报告 |
| ws_server 可测性说明 → 星验 | SU·实时·闪电 | 进行中 |

红线：跨人文件勿动，各自 commit；部署脚本永不代 commit。

## 8. 验证标准

- [ ] `/ds-bot-states` 数据进入 store（DevTools 可见）
- [ ] App.vue 无手写 fetch/WS 逻辑，统一走 useDSHBridge
- [ ] useBotStore 源码零 BOT_HOME_FLOOR 硬编码
- [ ] dsh_server 零 Flask 引用，:19003 端点行为不变
- [ ] vue-tsc 零错误，Vite build 通过
- [ ] 回溯计划：任一验证失败，git revert 对应 commit，链路退回 ws_server 单源模式
