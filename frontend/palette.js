/**
 * Star-Office-UI Palette v1
 * 统一颜色 Token — 像素办公室设计系统
 *
 * 所有视觉颜色在此文件中集中管理，不得在 game.js/index.html 中硬编码 hex 值。
 * 需配合 index.html 中的 AREA_POSITIONS 和 GUEST_SPRITE_MAP 使用。
 */

const PALETTE = {
  // ── 区域色（MUJI 自然色调） ──────────────
  area: {
    breakroom:   '#faf7f2',    // 休息区 — 米白
    writing:     '#f2f7f2',    // 办公区 — 淡绿
    executing:   '#f7f5f0',    // 执行区 — 浅木色
    researching: '#f5f3f7',    // 研究区 — 淡紫灰
    syncing:     '#f7fafc',    // 同步区 — 浅蓝灰
    error:       '#fef5f5',    // Bug 区 — 浅粉
  },

  // ── 状态色 ──────────────────────────────────
  status: {
    active:   '#5b8c5a',     // 工作中 — 森林绿
    idle:     '#b0a89c',     // 空闲 — 暖灰
    error:    '#d49592',     // 错误 — 柔和红
    syncing:  '#c4a96b',     // 同步中 — 暖金
    offline:  '#c5bfb6',     // 离线 — 浅灰褐
    pending:  '#a89cc4',     // 待授权 — 柔和紫
  },

  // ── Agent 角色色（柔和版本） ──────────────
  agent: {
    chief:     '#c8a45c',    // ⭐ Chief — 暖金
    star:      '#c8a45c',
    git:       '#6ba3a8',    // 🐙 Git — 青绿
    doc:       '#7ba87a',    // 📖 Readme — 叶绿
    gzh:       '#c48c9e',    // ✨ 排版 — 柔和粉
    ub:        '#c4926b',    // 🏗 UB — 暖橙
    vue:       '#7aacb8',    // 🟢 Vue — 柔和青
    remotion:  '#9c8cc4',    // 🎥 Remotion — 柔和紫
    ceo:       '#c4a85c',    // 💼 管理顾问 — 芥末黄
    designer:  '#c47c94',    // 🎨 设计 — 玫瑰粉
    aier:      '#8c8cc4',    // 🧠 AI — 薰衣草蓝
    curator:   '#7aac9c',    // 📦 知识管理者 — 鼠尾草绿
    dev:       '#7c9cc4',    // 🔧 软件工程师 — 柔和蓝
    techlead:  '#9c8cc4',    // 🧭 技术负责人 — 温和紫
    pm:        '#c47c7c',    // 📋 产品经理 — 柔和红
    sre:       '#c48c7c',    // 🛡 SRE — 暖陶红
    pix:       '#8c7cc4',    // 🎮 像素办公室 — 温和紫
    default:   '#b0a89c',    // 默认暖灰
  },

  // ── UI 组件色（日式自然） ──────────────────
  ui: {
    bg:         '#f5f0e8',   // 主背景 — 米白
    card:       '#faf7f2',   // 卡片 — 浅米
    accent:     '#8c7cc4',   // 强调色 — 温和紫
    text:       '#4a4036',   // 主文字 — 深褐
    muted:      '#9c9488',   // 次要文字 — 灰褐
    border:     '#d4cfc4',   // 边框 — 浅灰
    overlay:    'rgba(245,240,232,0.9)',
    wood:       '#c4b89c',   // 木色
    leaf:       '#8cac7c',   // 叶绿
    stone:      '#d4ccc0',   // 石色
  }
};

// ── 角色名 → 颜色快速映射 ──────────────────
const ROLE_COLOR_MAP = {
  'Chief':        PALETTE.agent.chief,
  'Git管家':      PALETTE.agent.git,
  'Readme管家':   PALETTE.agent.doc,
  '排版管家':     PALETTE.agent.gzh,
  'UB模式':       PALETTE.agent.ub,
  'Vue3专家':     PALETTE.agent.vue,
  'Remotion大师': PALETTE.agent.remotion,
  '管理顾问':     PALETTE.agent.ceo,
  '设计品味':     PALETTE.agent.designer,
  'AI工程师':     PALETTE.agent.aier,
  '知识管理者':   PALETTE.agent.curator,
  '软件工程师':   PALETTE.agent.dev,
  '技术负责人':   PALETTE.agent.techlead,
  '产品经理':     PALETTE.agent.pm,
  'SRE工程师':    PALETTE.agent.sre,
  '像素办公室':   PALETTE.agent.pix,
};

// ── 状态 → 区域映射 ────────────────────────
const STATE_TO_AREA_MAP = {
  idle:         'breakroom',
  writing:      'writing',
  researching:  'researching',
  executing:    'executing',
  syncing:      'syncing',
  error:        'error',
};

// ── 区域标签 ────────────────────────────────
const AREA_LABELS = {
  breakroom:   '🛋 休息区',
  writing:     '💻 写作区',
  researching: '🔍 研究区',
  executing:   '🔧 工作区',
  syncing:     '🔄 同步区',
  error:       '🐛 Bug 区',
};