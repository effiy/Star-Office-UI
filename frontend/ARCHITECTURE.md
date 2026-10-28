# Star Office UI — Vue 3 Architecture

## Directory Structure

```
frontend/
├── index.html           # Original standalone app (kept as reference)
├── game.js              # Phaser game (kept, loaded by usePhaserGame)
├── layout.js            # Game layout config (kept)
├── package.json         # Vue 3 + Vite + Pinia deps
├── vite.config.ts       # Vite dev server + proxy to Pixel Office
├── tsconfig.json        # TypeScript strict mode
├── ARCHITECTURE.md      # This file
├── src/
│   ├── main.ts          # Vue app entry (createApp + Pinia)
│   ├── App.vue          # Root: floor transitions + layout composition
│   ├── stores/
│   │   └── useBotStore.ts   # Pinia: bots, floors, selection, drawer
│   ├── composables/
│   │   └── usePhaserGame.ts # Bridge to game.js, resize observer
│   ├── components/
│   │   ├── OfficeLayout.vue # Main shell: stage + panels + drawer
│   │   ├── OfficeFloor.vue  # Floor nav buttons + content slot
│   │   ├── StatusPanel.vue  # Bot status list (compact/expanded)
│   │   ├── BotAvatar.vue    # Bot avatar button with pulse dot
│   │   ├── BotBubble.vue    # Popup bubble (detail tooltip)
│   │   └── BotInfoCard.vue  # Full bot info in drawer
│   └── styles/
│       └── unified-tokens.css  # Design tokens from original CSS
```

## Component Tree

```
App.vue
└── OfficeLayout.vue
    ├── [slot: default]
    │   └── <div id="game-container" />  ← Phaser canvas
    ├── OfficeFloor.vue
    │   └── [slot: default]
    │       └── (floor-specific content)
    ├── StatusPanel.vue
    │   └── BotAvatar.vue × N
    └── [drawer]
        ├── StatusPanel.vue (expanded)
        └── BotInfoCard.vue
            └── BotBubble.vue
```

## Data Flow

```
Pixel Office :19000/agents
    │  fetch every 30s
    ▼
useBotStore (Pinia)
    │  bots, currentFloor, selectedBotId
    ├──▶ StatusPanel → BotAvatar (list)
    ├──▶ BotInfoCard (detail)
    ├──▶ OfficeFloor (nav)
    └──▶ BotBubble (tooltip)
```

## Phaser Integration

`usePhaserGame` composable:
1. Loads `layout.js` + `game.js` dynamically
2. Phaser auto-creates into `#game-container` (provided by Vue)
3. ResizeObserver keeps canvas synced with container
4. Vue UI overlays (panels, drawer) float above canvas via z-index

## Key Decisions

- **No router** — single-page app, floor switching via Pinia state
- **No axios** — pure `fetch` for simplicity (Chief constraint)
- **Phaser kept as-is** — game.js/layout.js unchanged, loaded dynamically
- **Design tokens** extracted from original ~1100 lines of inline CSS
