# 第一波进度速记（ADR-002 迁移五步）

更新时间：2026-11-07 10:16（TL 第三轮取证 + 五项裁决）

| 步骤 | 负责 | 状态 |
|:---:|------|------|
| ① ws_server 修复 | 闪电 | ✅ 闭环（星验 103 用例全绿佐证，D4 门待星验回执一句话正式宣告） |
| ② Collector 双跑 | 铸舰 | 🟡 DSH 侧 LIVE；**缺陷 A**（roles 空：yi_ai_client 缺 X-Token + 走错 POST /roles-sync）修复中；**缺陷 B**（吃旧注册表，铁甲验收 total≥300/非idle>0/现行名出现）待修 |
| ③ 前端重指向 | 筑桥 | 🟡 **代码完成**（/api/v2/bot-states 迁移 + proxy→:19000 + TS 零错误），验证等 ② 数据修复 |
| ④ 退役 :19001/:19003 | 铸舰 | ⏸ 等 ③ 验证全绿 + 冻结公告。**TL 预检已清（10:35）**：YiVad 桥接文件 `/Users/yi/YrY/.ds-bot-states.json` 的写入方在**仓外**（agent 侧脚本，每分钟活跃更新，仓内 grep 零命中）——退役 :19001/:19003 **不触碰 YiVad 数据源**，无需跨界变更单；pyenv vs .venv 漂移实锤（sync_bridge 跑 pyenv 3.13.3，dsh_server 跑 .venv）——两者本就在退役集内，漂移随 ④ 自然消亡，**规范启动 env = .venv** 写进冻结报告即可 |
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
| 哲思 | a769e2b + 08e1341 + 本看板更新 | 裁决/取证 100%，第二波门禁未开 |
| 铁甲 | a5cb94d/2c641cd/14ed973/5d698f6（spec v1.3）+ YiAi 747e1ec | T1+鉴权细则+三缺陷诊断 100% |
| 闪电 | a953e3b（ws_server 重写+测试三件套） | SU-01 100%；ws_server 三层骨架（传输抽象 file/collector/redis + L2 过滤 + 富化）**collector 模式已启动验证中** |
| 铸舰 | **待补——backend 文件仍未 commit** | ② 95%：token✅ roles=328✅ R4 app.py 自加载 .env✅ B1 TcpFakeServer 可行✅；**缺陷 B 修复中**（bot-states 切 collector 实时数据） |
| 筑桥 | 76f21c4 + **P4 三件套待补 commit** | P1/P3/③/P4 100%：BotState.ts(185 行临时契约层) + useRoleStore(60s TTL+3 连败熔断) + gen-types.ts(冻结后一键重生成)，TS 零错误 build 533ms/55 modules，未碰 useBotStore（R5 合规） |
| 星绘 | 86c187c + f9ce7f4（T6+docs） | **100% 收口**，单写权已交棒；下一检查点=RoleTooltip 实数据联调（(b) 修复后 role_title 出现） |
| 星验 | **待补——契约测试+merge_engine tests commit** | **100%**：136 用例 / D4 门 ✅ CLEAR 正式宣告 / 7 态修正落地；下一件=SLO 延迟测试（铸舰 Collector 稳定后）+ ws_server 回归（闪电⑤后） |
| 签蟹 | 批次 B 已推送 e46631f..76f21c4（7 commit 上线） | 基线锚定进行中 |

## 冻结门数据（10:3x TL 第五轮取证——修正版）
- **(a) roles count>0**：✅ **CLOSED** — count=328
- **(b) 缺陷 B**：🟢 **数字三项全绿，待铁甲复测关账** — 10:36 终检：total=271（=live 源）/ non_idle=13 / **roleTitle 271/271（100%）**。铁甲「total≥300」重基线为「=live 源计数」
  - ⚠️ **复测核查点（TL 新增）**：100% 角色覆盖超出 §7 botId 绑定预期（晨间 43/316）——铁甲验证 join 语义：是 roles-sync 绑定已增长（合法），还是 collector 引入 name 兜底（=§7 偏离，角色卡错配风险）。若为后者：冻结公告必须钉死 join 语义，回退纯 botId join 或把 name 兜底显式合法化并加错配测试
  - ⚠️ 上轮 TL 报 with_role=0 为**探测假阴性**（snake_case 探针 vs camelCase API），特此修正入档
  - ✅ **floor 异常定性（10:4x）**：with_floor 5→271 — collector `_compute_floor` 本就是 hash 兜底（与 ws_server/useBotStore 同算法），早期快照 floor 键缺失是 enrichment 未统一，现已全量。**R7 不变**：registry 未再生成（11-04 旧文件，45/50 死名），策展 50 席仍归闪电脚本；注意 `frontend/dist/floor-registry.json`（10:22 构建副本）也是旧数据，R7 落地后需重新 build
- **(c) 7 态枚举**：✅ **CLOSED**
- **D4 门**：✅ **CLEAR**（136 pass 零 xfail）
- **R6 大小写裁决（TL）**：**wire 契约 = camelCase**（`roleTitle/agentId/updatedAt`——运行中 API 与前端临时字段已一致）；spec §3 BotState v1 的 snake_case 样例出**勘误**（闪电，spec 属主）；Pydantic 侧用 serialization alias 对齐 wire；冻结公告钉死 camelCase；星验契约测试补 wire-shape 断言
- **R7 floor-registry 腐化裁决（TL，根因已实锤）**：registry 50 席与 live DSH 271 名**重合仅 5**（=with_floor=5，严格互证）——45 席名字死于团队改名潮（Chief/AI工程师/Git管家/OKR管家→Git管家·签蟹/AI专家·铁甲…）。**collector 代码无罪**，纯数据腐化，且团队名册持续演化会复发。裁决：闪电（SU-04 属主）写 **`scripts/gen_floor_registry.py` 再生成脚本**（可持续，不手改一次性数据）：live DSH 名单 + 角色模式分楼（管理/管家/专家→1F 15 席；工程/SU·/YiVad·/工兵→2F 20 席；创意/设计/大师→3F 15 席）→ 产出候选 50 席 commit，铁甲+哲思抽查。**③ 实数据验证前落地**（否则办公室视图验证无意义）；期间 hash 兜底保稳定，无宕机风险。冻结报告附 registry 刷新 SOP 一段（第二波 YiVad 集成同样受名册漂移影响，此为前置教训）
- 冻结公告条件已齐：铸舰 commit backend + floor 诊断一句话 + 铁甲 (b) 复测关账 → 铸舰发公告（带 R2 两层数字 + R6 camelCase）→ 筑桥 codegen 重生成（diff 归零核查点）→ ③ 实数据验证 → ④ 退役 → ⑤ 两步走

## R3 Redis 基建进展
- **B1 确认可行**：铸舰实测 TcpFakeServer 基础读写 OK；PUBSUB 有阻塞待解
- **⑤ 拆两步**（TL 裁决）：闪电先以 **collector 模式**（已启动 ✅）完成广播瘦身 + stale 推送 + L2 50 席过滤——SLO 价值立即兑现；Redis SUBSCRIBE 作为传输层增强，待 PUBSUB 阻塞解决或真 Redis 落地后**一个开关切换**（传输抽象已就位），不作为第一波收口阻塞
