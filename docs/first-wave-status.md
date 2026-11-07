# 第一波进度速记（ADR-002 迁移五步）

更新时间：2026-11-07 10:10（重启窗后晨检，TL 取证）

| 步骤 | 负责 | 状态 |
|:---:|------|------|
| ① ws_server main() try/except 修复 | 闪电 | ✅ 修复+复跑（33 pass + 1 xfail 闭环）；星验正式复跑清 xfail → D4 门全开 |
| ② Collector @ :19000 双跑 | 铸舰 | 🟡 **DSH 侧 LIVE**（PID 27995 @ 08:55 新码，/health 含 yi_ai）；**YiAi join 断**：roles:[] 根因 = yi_ai_client 缺 `X-Token` 头（spec §7），修复中 |
| ③ vite proxy + useDSHBridge 重指向 :19000 | 筑桥 | ⏸ 等 ② 冻结（其间 P4：useRoleStore + codegen 工具链 + 组件壳） |
| ④ 退役 :19001/:19003 | 铸舰 | ⏸ 等 ③ 全绿 + D4 门 |
| ⑤ ws_server 切 Redis SUBSCRIBE + 瘦身 + stale | 闪电 | ⏸ 等 ④（:19002 重启窗后掉线已被闪电手动恢复，50 bot 注册，WS 实测可达） |

## 晨检关键事实（10:04 取证）
- **:19000 已跑新码**：PID 27995 @ 08:55:17，/health 含 `yi_ai` 段 → Collector lifespan 生效，DSH 侧 16 bots 出数
- **roles:[] 根因实锤**：直连 YiAi `/roles` → HTTP 401 `{"code":1009}`；代理 `/api/v2/yi-ai/roles` → `roles:[], count:0`。缺 §7 的 `X-Token: $YIAI_TOKEN` 头（token 源：`~/Library/LaunchAgents/com.yivad.yiai.plist` 的 API_X_TOKEN → 配到 `.env` 的 `YIAI_TOKEN`，永不进 git/前端）
- **/health 假阳性**：`yi_ai.available:true` 但鉴权拉取实际失败——按 §7 改暴露 `yiai_ok` / `yiai_cache_age_s`（反映真实鉴权路径结果）
- **join 覆盖率预期**：botId 绑定 43/316（roles-sync 每分钟刷新）——修复后未绑定 bot 角色字段为空是**合法状态**（前端正常渲染、无 tooltip），不是 bug
- **枚举裁定**（铁甲 spec §3，commit 14ed973）：线上 7 态；内部解析 6 态合法、发射侧必须 7 态、offline 显式派生——铸舰/星验各领一处修正
- **访问入口**（用户问题）：`http://127.0.0.1:19000`（主应用），WS 自动连 :19002

## 契约状态
- Pydantic 源：`backend/dsh_models.py`（DshBotState + MergedBotState）→ 铸舰升级 BotState v1 后群内宣布**冻结**
- 冻结公告三件套：① YiAi join 出数（roles count>0）② 端点版本定死（候选 `/ds-bot-states`:1373 vs `/api/v2/bot-states`:2294，TL 建议后者）③ 7 态枚举修正落地
- TS 侧：`frontend/src/types/BotState.ts` 冻结后由筑桥 codegen 生成，**禁止手写**
- 合并语义（TL 裁决）：`merge_engine.py` = 三源聚合规范模块（所有权铸舰、测试星验）；第一波 `_enrich_bot_state` 为活路径；冻结时优先级/降权常量必须同源引用
- 契约测试：46/46 绿；§7.1（commit 5d698f6）有 YiAi live 样例 + 4 条契约测试注意（断言 code 数值非 message / Mongo naive-ISO UTC→epoch ms 换算在 Collector / botId 空串合法 / join 用 botId 勿用 botName）——星验 mock_yiai 直接可用
- 变更单：11-07 00:56 已发跨项目联动枢纽（铁甲），待 mac·企鹅会签；YiAi 侧 commit 747e1ec（签蟹）

## 第二波（门禁：第一波验证标准全勾）
- 前端设计权威：筑桥 v2.1 方案 → 待落盘 docs/frontend-v2.1-design.md
- 伞形架构：redesign-v3-spec.md（YiVad 成果板/反向嵌入/徽章深链）
- yivad_connector：铸舰；yiai activity 流：铁甲 §8 预研已有结论
- 星绘 T6 已解锁（铁甲裁定）：角色卡 tooltip 数据面 + stale 灰显

## 并行支线
- 星绘：✅ P0 双项交付（tokens 35→73、ink-muted 4.5:1、SoToast 已接 App.vue 且 build 零回归）→ 下一步 SoModal/SoSpinner + T6
- 星验：复跑韧性清 xfail（开 D4 门）→ mock_yiai.py + test_yiai_contract.py（§7.1 样例直用）
- 闪电：⑤ SUBSCRIBE 骨架可预搭（`star:channel:state` PUBLISH 已定形）
- 铁甲：按 ADR-002 §4 验证标准对表验收（其自领角色）

## 12:00 回执（企鹅动员令）
各自 commit hash + 进度百分比。TL 回执：docs 四件套已 commit（见群消息）。
