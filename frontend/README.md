# Star-Office-UI 前端静态资源说明

> 像素办公室前端——基于 Phaser.js 的 2D 像素渲染引擎 + 原生 HTML/JS UI 层

## 目录结构

```
frontend/
├── index.html                  # 🏠 主看板页面——办公室全景视图
├── join.html                   # 🤝 访客加入页面——填写 Join Key 加入办公室
├── invite.html                 # 📨 邀请页面——生成邀请链接
├── electron-standalone.html    # 🖥️ Electron 桌面宠物版入口
│
├── game.js                     # 🎮 Phaser.js 游戏引擎主循环
│   ├── 地图层：Tiled 地图 + AI 背景叠加
│   ├── 角色层：spritesheet 动画（4帧 × 4方向 = 16帧/状态）
│   └── 碰撞检测：走近触发视频聊天/Avatar 互动
│
├── layout.js                   # 🏗️ 布局引擎——办公室区域划分与角色定位
│   ├── 休息区（breakroom）：沙发、咖啡机——idle 状态
│   ├── 工作区（workstation）：办公桌——executing/writing/researching/syncing
│   └── Bug 区（bugzone）：排错区——error 状态
│
├── palette.js                  # 🎨 调色板——MUJI 简约自然风格色彩系统
│
├── join-office-skill.md        # 📋 OpenClaw Skill——访客一键接入指南
│
├── btn-*-sprite.png            # 🔘 按钮精灵图（home/broker/diy/move/drawer/state）
├── cats-spritesheet.webp       # 🐱 像素猫角色精灵表
├── coffee-machine-*.webp       # ☕ 咖啡机精灵表（v3 网格布局）
├── desk-*.webp                 # 🪑 办公桌精灵表
├── error-bug-spritesheet-grid.webp  # 🐛 Bug 区精灵表
│
└── petdex_*.json               # 📇 像素角色配置（boba/eve/mallow/nickel/noir）
```

## 核心渲染流程

```
index.html 加载
    │
    ├── palette.js    → 初始化 MUJI 色彩系统
    ├── layout.js     → 计算办公室区域布局 + 角色初始位置
    ├── game.js       → 启动 Phaser.js 主循环
    │   ├── 加载 Tiled 地图层
    │   ├── 加载 AI 生成背景（如有）
    │   ├── 加载角色精灵表
    │   └── 注册状态轮询（每 3 秒）
    │
    └── 状态轮询 → GET /status + GET /agents → 角色动画更新
```

## 资源约定

| 类型 | 格式 | 命名规范 | 示例 |
|------|------|---------|------|
| 按钮精灵 | PNG（带 `-sprite` 后缀） | `btn-{功能}-sprite.png` | `btn-state-sprite.png` |
| 角色精灵 | WebP（spritesheet grid） | `{角色名}-spritesheet.webp` | `cats-spritesheet.webp` |
| 家具精灵 | WebP（grid 布局） | `{家具名}-v{版本}-grid.webp` | `coffee-machine-v3-grid.webp` |
| 角色配置 | JSON | `petdex_{名称}.json` | `petdex_mallow.json` |
| 精灵兼容链接 | 软链接 | `{旧名}.webp → {新名}.webp` | `desk.webp → desk-v3.webp` |

## 性能指标

| 指标 | 数值 | 说明 |
|------|:---:|------|
| 同屏 Agent 上限 | ≤ 16 | Phaser.js sprite batching 上限 |
| 帧率 | 60fps | 16 Agent 同屏稳定 |
| 状态轮询间隔 | 3 秒 | 增量更新避免闪烁 |
| 移动端适配 | ✅ | 视口完美自适应 |
| 多语言 | CN/EN/JP | HTML `lang` 属性 + JS 文案联动 |

## 添加新角色

1. 准备 4 帧 × 4 方向的 spritesheet（推荐 WebP 格式）
2. 创建 `petdex_{角色名}.json` 配置文件
3. 在 `game.js` 中注册角色类型
4. 软链接旧文件名（兼容已有引用）

详见 [convert_to_webp.py](../convert_to_webp.py) 图片转换脚本。

---

## DSH Bot 像素角色映射

| DSH Bot | 像素角色 | Spritesheet | 配置文件 |
|---------|---------|------------|---------|
| Chief | 👑 骑士 | star-working-spritesheet-grid.webp | petdex_mallow.json |
| Git管家 | 🐙 章鱼 | star-working-spritesheet-grid.webp | petdex_boba.json |
| Readme管家 | 📝 文书 | star-working-spritesheet-grid.webp | petdex_eve.json |
| 知识管理者 | 📚 智者 | star-working-spritesheet-grid.webp | petdex_boba.json |
| 软件工程师 | 💻 开发者 | star-working-spritesheet-grid.webp | petdex_nickel.json |
| AI工程师 | 🤖 AI | star-working-spritesheet-grid.webp | petdex_noir.json |
| Vue3专家 | 🟢 代码忍者 | star-working-spritesheet-grid.webp | petdex_mallow.json |
| Remotion大师 | 🎥 导演 | star-working-spritesheet-grid.webp | petdex_eve.json |
| 排版管家 | ✨ 排版精灵 | star-working-spritesheet-grid.webp | petdex_boba.json |
| 管理顾问 | 💼 CEO | star-working-spritesheet-grid.webp | petdex_nickel.json |
| SRE工程师 | 🔧 运维 | star-working-spritesheet-grid.webp | petdex_noir.json |
| 技术负责人 | 🏗️ 架构师 | star-working-spritesheet-grid.webp | petdex_mallow.json |
| 产品经理 | 📋 PM | star-working-spritesheet-grid.webp | petdex_eve.json |
| 设计品味 | 🎨 设计师 | star-working-spritesheet-grid.webp | petdex_boba.json |
| 像素办公室 | 🏢 办公室 | star-working-spritesheet-grid.webp | petdex_boba.json |
| UB模式 | 🔒 安全 | star-working-spritesheet-grid.webp | petdex_noir.json |

> 状态驱动的动画切换由 `game.js` 的 `set_state` 事件处理，详见 `backend/dsh_bridge.py`。