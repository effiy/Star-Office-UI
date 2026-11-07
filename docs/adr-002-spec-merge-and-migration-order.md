# ADR-002: 双规格合一 + 单管线迁移顺序

- 状态：已接受
- 日期：2026-11-07
- 决策人：技术管家·哲思（TL）
- 背景：同一夜出现两份重设计规格——`redesign-v3-spec.md`（哲思，三环模型/OfficeEvent/四期）与 `data-integration-spec.md`（闪电，单管线/BotState v1/T1-T6）。两者互补但枢纽设计与契约命名冲突，必须合一，防止两队各跑一张图。

## 1. 问题陈述

- 闪电方案更锋利：Collector 并入 FastAPI lifespan，退役 :19001/:19003，ws_server 从 500ms 文件轮询改 Redis SUBSCRIBE（<50ms），广播瘦身 60%+，BotState v1 做 DSH⋈YiAi 角色卡 join
- 哲思方案更全面：覆盖 YiVad 第三线（成果板/事件特效/反向嵌入），但枢纽层设计（connectors 保留 :19003）弱于闪电的单管线
- 冲突点：① Hub 拓扑（保留 dsh_server vs 退役）② 契约（OfficeEvent vs BotState v1）③ 筑桥刚交付的 vite proxy→:19003 与退役计划相撞

## 2. 决策

### D1 — 第一波 Hub 采纳闪电单管线设计
`data-integration-spec.md` 为**第一波（DSH⋈YiAi）实施权威**。Collector 唯一摄取点 + Redis PUB/SUB + ws_server SUBSCRIBE。:19001（sync_bridge/ds_bot_watcher）与 :19003（dsh_server）在迁移完成后退役。
理由：彻底消灭 3 份冗余轮询（比 ADR-001 D6「收敛到 2」更进一步）；事件驱动延迟 <50ms；单摄取点=单降级面，可测性最好。

### D2 — 规范状态契约冻结为 BotState v1，OfficeEvent 信封推迟到第二波
第一波只有一种流：bot 状态快照。BotState v1（Pydantic 为源，TS 由 codegen 生成——筑桥 T4）即唯一契约。OfficeEvent 多源事件信封（activity/achievement/effect）**推迟**到第二波 YiVad 成果/特效事件出现时再引入，避免过早抽象。
`redesign-v3-spec.md` 保留为**伞形架构 + 第二波（YiVad 效果环/反向集成）权威**。

### D3 — 迁移顺序为硬性红线（五步，各自独立 commit）
```
① 闪电修 ws_server main() bridge-state.json 读取缺 try/except（星验 xfail 转绿）
② 铸舰建 Collector 于 :19000 lifespan，在 :19000 上暴露同契约 /ds-bot-states
   （:19003 此时仍活着——并行双跑，不动现有链路）
③ 筑桥把 vite proxy + useDSHBridge 从 :19003 重指向 :19000，回归全绿
④ 铸舰退役 :19001/:19003（ds_bot_watcher / sync_bridge / dsh_server 标记废弃）
⑤ 闪电 ws_server 切 Redis SUBSCRIBE + 广播瘦身（avatar→URL+ETag）+ stale 推送
```
回滚：任一步失败 revert 该步 commit，前序状态仍可运行。②③ 之间双跑期不限时，以 ③ 全绿为 ④ 的前置门。

### D4 — 星验测试门与企鹅裁决的衔接
mac·企鹅 裁决「轮询收敛排第二波等星验测试全绿」。解释：**建造** Collector（步骤②）不受门限，**退役**（步骤④）受门限——门=步骤①落地且韧性套件无 xfail。当前 23/23 单元 + 6/6 集成 + 5/5 韧性（1 xfail）距全绿仅差闪电一个 5 分钟修复。

### D5 — YiAi `/roles` 端点合规补票
铁甲 T1 已在 YiAi `src/server/routes/roles.py` 落地 GET /roles + /roles/{id}（:343/:376）。按企鹅红线「YiAi 只读侦查，接入须走跨项目变更单」——**补变更单**，铁甲主笔、企鹅会签。Collector 侧无论票况如何都按外部契约对待：60s TTL 缓存 + 熔断降级（星验 T5 已覆盖熔断测试）。

## 3. 分工（合并 T1-T6 与 P0-P4）

| 人 | 即刻 | 第一波后续 | 第二波 |
|----|------|-----------|--------|
| 闪电 | ①修 ws_server bug | ⑤SUBSCRIBE+瘦身+stale；总线压测 | dsh_connector 抽离收尾 |
| 铸舰 | ②Collector+双跑 | ④退役 :19001/:19003 | yivad_connector（成果数据） |
| 筑桥 | T4：BotState v1 codegen（Pydantic→TS） | ③proxy/bridge 重指向 | 气泡动效+事件特效 |
| 星验 | ①后复跑韧性套件→全绿 | T5：契约+SLO+YiAi 熔断测试 | 降级演练扩展 YiVad 源 |
| 星绘 | 收口 tokens+SoToast（已 GO） | T6：角色卡 tooltip+stale 灰显 | 成果板+OfficeOverlay |
| 铁甲 | D5 变更单补票 | /roles 鉴权细则→Collector 凭证配置 | yiai activity 流调研 |
| mac·企鹅 | D4/D5 会签 | — | P4 YiVad 跨群协调 |

## 4. 验证标准

- [ ] ①后：星验韧性套件 0 xfail
- [ ] ③后：前端从 :19000 拿到 /ds-bot-states，WS/REST 双路径回归全绿，vue-tsc 零错误
- [ ] ④后：`lsof -i:19001 -i:19003` 无监听，DSH 文件轮询循环=1（Collector）
- [ ] ⑤后：广播体积 ↓60%+，事件驱动延迟 <50ms（压测报告），stale>10s 正确标记
- [ ] 端到端：DSH 跑任务 → 办公室精灵 <50ms 响应 + 角色卡 tooltip 显示 YiAi role_title/redlines

## 5. 回溯计划

五步各自独立 commit；任何验证失败 revert 对应步骤，双跑期架构（②③之间）是天然安全岛。第二波任何部分不启动，直到第一波验证标准全勾。
