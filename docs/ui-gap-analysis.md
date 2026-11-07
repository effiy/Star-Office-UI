# Star Office UI — 设计规范缺口分析

> 审计日期：2026-11-07 | 基准：`docs/ui-components.md` + `unified-tokens.css` + 10 个 Vue 组件源码
> 设计参照：MUJI 极简自然风格 + 用户偏好「简洁清新自然的视觉风格」

---

## 一、执行摘要

| 维度 | 评分 | 说明 |
|------|:---:|------|
| 组件覆盖率 | 🟡 60% | 10 个组件够用当前 MVP，但缺基础设施组件 |
| CSS Token 覆盖率 | 🟡 65% | 颜色/间距/字体有体系，缺状态层/z-index/断点 |
| MUJI 风格对齐 | 🟡 50% | 色调方向对（暖米），但像素游戏风格与 MUJI 极简冲突 |
| 组件一致性 | 🔴 40% | 命名混乱、硬编码泛滥、无统一 BEM 规范 |

**结论**：当前组件可支撑 MVP 运行，但扩展性和专业度不足。修复优先级：Token 补全（P0）→ 命名规范统一（P0）→ 基础设施组件补齐（P1）→ MUJI 风格调和（P2）。

---

## 二、CSS Token 缺口分析

### 2.1 已有 Token（✅）

| 分类 | Token 数量 | 覆盖面 |
|------|:---:|------|
| 颜色 | 15 | 品牌/语义色全 |
| 字体 | 6 | 像素+等宽+字号阶梯 |
| 间距 | 6 | xs→lg 阶梯合理 |
| 圆角 | 3 | sm→lg 阶梯 |
| 过渡 | 2 | 快/慢两种 |
| 阴影 | 3 | sm→lg 阶梯 |

### 2.2 缺失 Token（🔴 P0）

| Token | 建议值 | 原因 |
|------|------|------|
| `--so-focus-ring` | `0 0 0 2px var(--so-accent)` | **无障碍合规** — 当前无任何 focus 样式 |
| `--so-focus-ring-offset` | `2px` | 与 focus-ring 配套 |
| `--so-z-canvas` | `1` | Z-index 散落（1/10/50/100/999），无体系 |
| `--so-z-ui` | `10` | — |
| `--so-z-bubble` | `50` | — |
| `--so-z-drawer` | `100` | — |
| `--so-z-overlay` | `500` | — |
| `--so-z-modal` | `999` | — |
| `--so-breakpoint-sm` | `600px` | 响应式断点硬编码（600px/768px） |
| `--so-breakpoint-md` | `768px` | — |
| `--so-breakpoint-lg` | `1024px` | — |
| `--so-font-weight-normal` | `400` | 当前仅用 600/700，缺标准阶梯 |
| `--so-font-weight-semibold` | `600` | — |
| `--so-font-weight-bold` | `700` | — |
| `--so-line-height-tight` | `1.2` | 多行文本无行高控制 |
| `--so-line-height-normal` | `1.5` | — |
| `--so-border-width` | `1px` | 硬编码在 6 个组件中 |
| `--so-state-hover` | `rgba(0,0,0,0.04)` | 悬停态无统一背景色 |
| `--so-state-active` | `rgba(0,0,0,0.08)` | 激活态无统一背景色 |
| `--so-state-disabled` | `0.4` | 禁用态透明度散落（0.4/0.5） |

### 2.3 设计 Token 缺失（🟡 P1）

| Token | 建议值 | 原因 |
|------|------|------|
| `--so-font-sans` | `"Inter", "SF Pro", sans-serif` | **MUJI 风格关键** — 当前仅像素字体，缺无衬线正文 |
| `--so-icon-size-sm` | `14px` | 图标尺寸无统一管理 |
| `--so-icon-size` | `18px` | — |
| `--so-icon-size-lg` | `24px` | — |
| `--so-animation-duration` | `200ms` | 动画参数分散在各组件 |
| `--so-animation-easing` | `cubic-bezier(0.4,0,0.2,1)` | — |
| `--so-container-sm` | `640px` | 内容最大宽度无约束 |
| `--so-container-md` | `960px` | — |
| （暗色主题） | 完整 `[data-theme="dark"]` 覆盖 | 当前仅 `--so-dark-bg`（仅 Phaser 画布用） |

---

## 三、组件一致性审计

### 3.1 CSS Class 命名规范混乱

每个组件使用不同的缩写前缀，无统一 BEM 或命名系统：

| 组件 | 前缀 | 示例 |
|------|------|------|
| OfficeLayout | `sol` | `.sol-loading__text` |
| StatusPanel | `ssp` | `.ssp-badge--online` |
| BotAvatar | `sba` | `.sba.is-selected` |
| BotBubble | `sbb` | `.sbb--left` |
| BotInfoCard | `sbic` | `.sbic-header` |
| OfficeFloor | `sof` | `.sof-btn__count` |
| ErrorBoundary | `sbe` | `.sbe-card` |
| YesterdayMemo | `sym` | `.sym-loading__dot` |
| JoinPanel | `sjn` | `.sjn-card` |
| PhaserCanvas | — | `.phaser-canvas` |

**问题**：
- 前缀命名不统一（有的 3 字母，有的语义化）
- 修饰符混用 `--`（BEM 风格）和 `.is-*`（SMACSS 风格）
- `phaser-canvas` 与其他 `s**` 前缀不一致
- OfficeView 使用 `sov` 但不在 components 目录

### 3.2 硬编码值清单（🔴 需要统一）

| 文件 | 硬编码 | 应替换为 |
|------|------|------|
| `JoinPanel.vue:176` | `backdrop-filter: blur(4px)` | `var(--so-glass-blur)` |
| `JoinPanel.vue:181` | `backdrop-filter: blur(10px)` | 新增 `--so-glass-blur-lg` |
| `JoinPanel.vue:183` | `border-radius: 16px` | `var(--so-radius-xl)` 或 token |
| `JoinPanel.vue:184` | `padding: 28px 32px` | `var(--so-padding-lg)` |
| `JoinPanel.vue:234` | `border-radius: 8px` | `var(--so-radius)` |
| `YesterdayMemo.vue:78` | `backdrop-filter: blur(6px)` | `var(--so-glass-blur)` |
| `YesterdayMemo.vue:80` | `border-radius: 12px` | `var(--so-radius-lg)` |
| `BotBubble.vue:29` | `padding: 10px` | `var(--so-padding)` |
| `BotBubble.vue:29` | `max-width: 260px` | 设计 token |
| `BotAvatar.vue:26` | `padding: 4px 10px` | 拆为 `--so-gap-xs` + `--so-gap` |
| `StatusPanel.vue:34` | `padding: 8px` | `var(--so-gap-sm)` |
| `StatusPanel.vue:37` | `border-radius: 10px` | `var(--so-radius)` |
| `OfficeFloor.vue:45` | `padding: 8px var(--so-padding-lg)` | — (部分硬编码) |
| `OfficeFloor.vue:47` | `gap: 6px` | `var(--so-gap-xs)` |
| `ErrorBoundary.vue:75` | `padding: 40px 20px` | 设计 token |
| `OfficeLayout.vue:63` | `border-radius: 2px` | `var(--so-radius-sm)` |
| `OfficeLayout.vue:50` | `width: max(320px, 30vw)` | 设计 token |

**总计：17 处硬编码值分布在 8 个组件中**。

### 3.3 CSS 变量 Fallback 不统一

- **有 fallback 的组件**（5 个）：JoinPanel、YesterdayMemo → `var(--so-ink, #3d3929)`
- **无 fallback 的组件**（5 个）：BotAvatar、StatusPanel、BotInfoCard、ErrorBoundary、OfficeLayout → `var(--so-ink)`
- 这种不一致导致：如果 `unified-tokens.css` 加载失败，一半组件会丢失颜色，另一半回退到硬编码值

---

## 四、缺失的基础设施组件

### 4.1 高优先级缺失（🔴 P0 — 阻塞日常 UX）

| 组件 | 用途 | 当前替代方案 |
|------|------|------|
| **SoToast / SoNotification** | 操作反馈、错误提示 | `console.warn` / `botStore.error` |
| **SoModal / SoDialog** | 确认对话框（删除/退出等） | JoinPanel 是唯一弹窗，且不是通用组件 |
| **SoSpinner / SoSkeleton** | 加载占位符 | OfficeLayout 内部的 `.sol-loading__bar`（全局唯一，不可复用） |

### 4.2 中优先级缺失（🟡 P1 — 阻碍功能扩展）

| 组件 | 用途 | 场景 |
|------|------|------|
| **SoTooltip** | 悬停提示 | Bot 卡片超长信息、按钮功能说明 |
| **SoBadge** | 状态标记 | Bot 状态计数、新消息提示 |
| **SoEmpty** | 空状态占位 | 无 Bot 在线、无昨日日记 |
| **SoProgress** | 进度条 | 资源加载进度（当前仅 asset store 有数据，无 UI） |
| **SoToggle** | 开关控件 | 暗色模式、通知开关 |
| **SoDropdown** | 下拉菜单 | 楼层筛选、Bot 排序 |

### 4.3 低优先级缺失（🟢 P2 — 锦上添花）

| 组件 | 场景 |
|------|------|
| SoTable / SoDataList | Bot 列表表格视图 |
| SoSearch | Bot 名称搜索 |
| SoSettingsPanel | 用户偏好设置 |
| SoThemeSwitcher | 亮/暗色切换 |
| SoSkipLink | 无障碍跳过导航 |

---

## 五、MUJI 风格对齐分析

### 5.1 用户偏好 vs 当前实现

| 用户偏好 | 当前实现 | 偏差 |
|------|------|:---:|
| 简洁清新自然 | 暖米色调 ✅ | 无偏差 |
| 避免繁复 | 玻璃拟态 + 多重阴影 | 🔴 中等偏差 |
| 自然色调 | `#f5f0eb` / `#d4c5b9` ✅ | 色调方向对 |
| — | 像素字体 (ArkPixel) | 🟡 项目特色，但缺无衬线备选 |
| — | 游戏化 UI（像素画布、状态指示灯） | 🟡 与"简洁"有张力 |

### 5.2 MUJI 调和建议

| 优先级 | 改动 | 影响 |
|:---:|------|------|
| P1 | 新增 `--so-font-sans` + 在正文区域使用无衬线字体 | 文字可读性↑ |
| P1 | 减少 backdrop-filter 层数（当前 3 层玻璃叠加） | 性能↑ 视觉↓ |
| P2 | 阴影从三层简化为两层（sm + lg） | 扁平化 |
| P2 | 圆角统一为 `var(--so-radius)`（当前有 2/4/8/10/12/16px 六种） | 一致性↑ |
| P2 | 提供「素色模式」（关闭玻璃拟态和游戏元素） | 用户可选 |

> ⚠️ **设计决策点**：像素办公室的核心卖点是「像素+游戏化」，与 MUJI 极简存在天然张力。建议保留像素主题作为默认，同时通过 token 体系让用户可切换到素色模式，而非强制统一。

---

## 六、可访问性 (a11y) 审计

| 问题 | 严重度 | 文件 |
|------|:---:|------|
| 无 focus-visible 样式（按钮全是 `outline: none` 等价） | 🔴 | BotAvatar, BotInfoCard, OfficeFloor |
| `aria-label` 仅 JoinPanel 有关闭按钮 | 🟡 | 全局 |
| `role` 属性缺失（BotAvatar 是 `<button>` 但无 `role="button"` 明确声明） | 🟢 | BotAvatar |
| 键盘导航依赖原生 `<button>` 行为（无自定义键盘处理） | 🟡 | 全局 |
| 颜色对比度：`--so-ink-muted` (#8b8680) 在 `--so-bg` (#f5f0eb) 上仅 **3.2:1**（WCAG AA 要求 4.5:1） | 🔴 | 统一 token |

---

## 七、优先级行动计划

### P0 — 本周必做（阻塞专业发布）

1. **补全 CSS Token**（`docs/ui-components.md` 末尾的「设计规范总结」→ 补充 z-index scale / focus-ring / breakpoints / font-weight / line-height / state layers）
2. **统一 CSS Class 命名**：全部改为 `so-{component}` 前缀（如 `sol-`→`so-layout-`，`ssp-`→`so-status-`）
3. **创建 SoToast 组件**（替换掉 `botStore.error` 的静默失败和 console.warn）
4. **修复颜色对比度**：`--so-ink-muted` 加深至 `#6b6560` 或更高

### P1 — 下周（提升专业度）

5. **创建 SoModal + SoSpinner + SoBadge 组件**
6. **添加 focus-visible 全局样式** + 键盘导航增强
7. **消除 17 处硬编码值**，全部收敛到 `unified-tokens.css`
8. **统一 CSS variable fallback 策略**（全有或全无）

### P2 — 后续迭代

9. **MUJI 素色模式**（`[data-theme="plain"]` 去掉玻璃拟态/阴影）
10. **Storybook / Histoire 组件展示**
11. **暗色主题完整实现**

---

## 附录 A：CSS Token 补全参考（建议追加到 `unified-tokens.css`）

```css
:root {
  /* ── Z-Index Scale ── */
  --so-z-canvas: 1;
  --so-z-ui: 10;
  --so-z-bubble: 50;
  --so-z-drawer: 100;
  --so-z-overlay: 500;
  --so-z-modal: 999;

  /* ── Breakpoints ── */
  --so-breakpoint-sm: 600px;
  --so-breakpoint-md: 768px;
  --so-breakpoint-lg: 1024px;

  /* ── Typography (扩展) ── */
  --so-font-sans: "Inter", "SF Pro Text", -apple-system, sans-serif;
  --so-font-weight-normal: 400;
  --so-font-weight-semibold: 600;
  --so-font-weight-bold: 700;
  --so-line-height-tight: 1.2;
  --so-line-height-normal: 1.5;

  /* ── Accessibility ── */
  --so-focus-ring: 0 0 0 2px var(--so-accent);
  --so-focus-ring-offset: 2px;

  /* ── State Layers ── */
  --so-state-hover: rgba(0, 0, 0, 0.04);
  --so-state-active: rgba(0, 0, 0, 0.08);
  --so-state-disabled: 0.4;

  /* ── Borders ── */
  --so-border-width: 1px;
  --so-border-width-thick: 2px;

  /* ── Icons ── */
  --so-icon-sm: 14px;
  --so-icon: 18px;
  --so-icon-lg: 24px;

  /* ── Animation ── */
  --so-duration-fast: 150ms;
  --so-duration: 200ms;
  --so-duration-slow: 350ms;
  --so-easing-standard: cubic-bezier(0.4, 0, 0.2, 1);
  --so-easing-decelerate: cubic-bezier(0, 0, 0.2, 1);
  --so-easing-accelerate: cubic-bezier(0.4, 0, 1, 1);
}
```

---

## 附录 B：组件命名规范建议

统一为 `So{Name}` 前缀 + scoped 内用 BEM：

| 当前 | 建议 |
|------|------|
| `OfficeLayout.vue` | → 保持，无需改名 |
| `StatusPanel.vue` → `ssp` | → `so-status` |
| `BotAvatar.vue` → `sba` | → `so-avatar` |
| `BotBubble.vue` → `sbb` | → `so-bubble` |
| `BotInfoCard.vue` → `sbic` | → `so-bot-card` |
| `OfficeFloor.vue` → `sof` | → `so-floor` |
| `ErrorBoundary.vue` → `sbe` | → `so-error` |
| `YesterdayMemo.vue` → `sym` | → `so-memo` |
| `JoinPanel.vue` → `sjn` | → `so-join` |
| `PhaserCanvas.vue` → — | → `so-phaser` |

> 迁移策略：新增 `so-*` class 同时保留旧的 `s**` class，渐进式迁移，不破坏现有功能。

---

> 审计完成。下一步：等待技术管家确认 P0 优先级，拿到 go-ahead 后开始 Token 补全 + SoToast 组件开发。