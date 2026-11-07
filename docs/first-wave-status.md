# 第一波进度速记（ADR-002 迁移五步）

更新时间：2026-11-07 10:16（TL 第三轮取证 + 五项裁决）

| 步骤 | 负责 | 状态 |
|:---:|------|------|
| ① ws_server 修复 | 闪电 | ✅ 闭环（星验 103 用例全绿佐证，D4 门待星验回执一句话正式宣告） |
| ② Collector 双跑 | 铸舰 | 🟡 DSH 侧 LIVE；**缺陷 A**（roles 空：yi_ai_client 缺 X-Token + 走错 POST /roles-sync）修复中；**缺陷 B**（吃旧注册表，铁甲验收 total≥300/非idle>0/现行名出现）待修 |
| ③ 前端重指向 | 筑桥 | 🟡 **代码完成**（/api/v2/bot-states 迁移 + proxy→:19000 + TS 零错误），验证等 ② 数据修复 |
| ④ 退役 :19001/:19003 | 铸舰 | ⏸ 等 ③ 验证全绿 + D4 门（双跑期活着是合法状态，非「声明与实态冲突」） |
| ⑤ ws_server SUBSCRIBE | 闪电 | 🔴 **被基建阻塞**：本机无真 Redis，fakeredis 进程内内存跨不了进程 → 见裁决 R3 |

## TL 五项裁决（10:16）

**R1 — 冻结门 = 三件**：(a) roles count>0（X-Token 修复，配方=spec §7：plist API_X_TOKEN → `.env` 的 `YIAI_TOKEN`，永不进 git/前端/群聊明文）(b) 缺陷 B 修复（对齐铁甲验收）(c) 7 态枚举落地（星验领修 + 铸舰发射侧）。**端点版本已事实定案**：`/api/v2/bot-states` = canonical（筑桥已迁 + 铁甲「双跑期 legacy 合法」），`/ds-bot-states` 保留为 legacy 别名至 ④。

**R2 — 契约分两层**（调和铁甲 total≥300 与办公室 50 容量）：
- L1 镜像层：collector→存储 = **全量 DSH bots**（~271+，权威镜像，任何消费方可用）
- L2 办公室视图：ws_server 广播 = **floor-registry 50 席过滤**（AgentPool 上限，策展视图）
- 冻结公告必须同时钉死两层各自的验收数字

**R3 — Redis 基建裁决**（新发现：本机无 redis-server/cli/brew/docker）：
- fakeredis=进程内内存 → ⑤ 的跨进程 PUB/SUB **当前物理不可能**
- 铸舰按序评估：**B1** fakeredis TCP server 模式（零系统安装、依赖已在）→ **B2** `brew install redis`（受阻走 H1 上报+替代方案）→ **B3** 推迟⑤，ws_server 维持 file-watch（500ms SLO 已达标，无回归）
- ①-④ 不被此阻塞：HTTP 路径走 collector 进程内缓存（铸舰已修）+ json-files 降级；ws_server 有自己的 watch

**R4 — 环境变量持久化**：`.env` 写入 `YIAI_TOKEN` + `STAR_USE_FAKEREDIS=1`；**app.py 自加载 .env**（launcher 无关，堵死 bridge-watchdog 裸拉起丢 env 这一类问题）；start-v2.sh 已 source .env（:13-14）不变

**R5 — 领地边界**：
- 筑桥 P4 **GO 但砍范围**：useEffectStore 属第二波（原裁决不变），本轮验收=BotState.ts codegen **工具链**（生成动作等冻结）+ useRoleStore（RoleCard 接口按 §7.1 样例，已稳定）
- 星绘 T6 GO 但 **shared types/ 禁区**：Bot 接口 role 字段等筑桥 codegen 统一生成；期间用组件文件内局部 interface + optional 消费。useBotStore.ts **单写者规则**：本轮星绘持笔（staleBotIds computed），筑桥勿入直至她回帖
- 签蟹：12:00 回执前发布 **文件→属主映射表**，各自 commit 各自文件（动员令解除旧「等批量」限制，基线锚定仍是你的活）

## 12:00 回执簿（企鹅动员令：commit hash + 进度%）
| 人 | commit | 进度 |
|----|--------|------|
| 哲思 | a769e2b + 本看板更新 | 裁决/取证 100%，第二波门禁未开 |
| 铁甲 | a5cb94d/2c641cd/14ed973/5d698f6（spec v1.3）+ YiAi 747e1ec | T1+鉴权细则+三缺陷诊断 100% |
| 闪电 | 待补（ws_server 修复+恢复 :19002） | SU-01 100%，⑤ 被 R3 阻塞 |
| 铸舰 | 待补（collector/merge_engine/yi_ai_client/app.py v2 端点） | ② 80%（缺陷 A/B 修复中） |
| 筑桥 | 待补（useDSHBridge/useBotStore/App.vue/vite.config/③迁移） | P1/P3/③代码 100%，P4 开工 |
| 星绘 | 待补（tokens 73/SoToast/SoTooltip/stale 灰显） | P0 100%，T6 60% |
| 星验 | 待补（103 用例/契约测试/merge_engine 测试） | 基线 100%，7 态修正中 |
| 签蟹 | 待补（两仓基线锚定） | 进行中 |
