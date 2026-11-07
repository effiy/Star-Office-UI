/**
 * OfficeScene — Phaser scene replacing game.js
 *
 * SU-03: Vue 3 + Phaser hybrid — managed by PhaserCanvas.vue
 * SU-04: AgentPool + zone-based culling for ≤50 agents
 *
 * Architecture:
 * - Scene config object (Phaser 3 compatible) created by createOfficeScene()
 * - SceneManager handles agent pool, viewport culling, Pinia sync
 * - Floor-based culling: only agents on the current floor are rendered
 */

import { AgentPool } from "./AgentPool";
import {
  OFFICE_LAYOUT,
  AGENT_ZONES,
  computeStableAgentPosition,
} from "./layout";
import type { Bot, FloorId } from "../stores/useBotStore";
import { FLOOR_CONFIG } from "../stores/useBotStore";

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

export interface SceneManagerAPI {
  /** Sync agent sprites with Pinia bot store data */
  syncAgents(bots: Bot[]): void;
  /** Switch floor visibility (culls agents outside current floor) */
  setFloor(floor: FloorId): void;
  /** Resize the game canvas */
  resize(width: number, height: number): void;
  /** Get current agent count stats */
  getStats(): { activeAgents: number; poolSize: number; fps: number };
  /** Get the Phaser.Game instance */
  getGame(): Phaser.Game;
}

// ═══════════════════════════════════════════════════════════════
// Zone ↔ Floor mapping
// ═══════════════════════════════════════════════════════════════

const FLOOR_ZONE_MAP: Record<FloorId, number> = {
  "1F": 0, // Management zone
  "2F": 1, // Engineering zone
  "3F": 2, // Creative zone
};

const FLOOR_Y_RANGES: Record<FloorId, { min: number; max: number }> = {
  "1F": { min: 40, max: 240 },
  "2F": { min: 260, max: 480 },
  "3F": { min: 500, max: 696 },
};

// ═══════════════════════════════════════════════════════════════
// WebP detection
// ═══════════════════════════════════════════════════════════════

function detectWebP(): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src =
      "data:image/webp;base64,UklGRkoAAABXRUJQVlA4WAoAAAAQAAAAAAAAAAAAQUxQSAwAAAABBxAR/Q9ERP8DAABWUDggGAAAADABAJ0BKgEAAQADADQlpAADcAD++/1QAA==";
  });
}

// ═══════════════════════════════════════════════════════════════
// Scene manager — core logic separated from Phaser lifecycle
// ═══════════════════════════════════════════════════════════════

class SceneManager {
  private scene: any; // Phaser.Scene (typed loosely for compatibility)
  private pool!: AgentPool;
  private currentFloor: FloorId = "1F";
  private game!: Phaser.Game;

  // Furniture / decor refs
  private sofa: any = null;
  private starWorking: any = null;
  private syncAnim: any = null;
  private errorBug: any = null;
  private serverroom: any = null;

  // Metrics
  private frameCount = 0;
  private lastFpsTime = 0;
  private currentFps = 0;

  // Agent zone assignment tracking
  private agentZones: Map<string, { zoneIndex: number; index: number }> = new Map();

  init(scene: any, game: Phaser.Game, supportsWebP: boolean) {
    this.scene = scene;
    this.game = game;
    this.pool = new AgentPool(scene, 50);
  }

  // ── Preload ──────────────────────────────────────────────

  preloadAssets(supportsWebP: boolean) {
    const ext = (name: string) => {
      if (OFFICE_LAYOUT.forcePng[name.replace(/\.(png|webp)$/, "") as keyof typeof OFFICE_LAYOUT.forcePng]) {
        return ".png";
      }
      return supportsWebP ? ".webp" : ".png";
    };

    const base = "/static/";

    this.scene.load.image("office_bg", `${base}office_bg_small${supportsWebP ? ".webp" : ".png"}`);
    this.scene.load.spritesheet("star_idle", `${base}star-idle-spritesheet${ext("star-idle-spritesheet.png")}`, {
      frameWidth: 128, frameHeight: 128,
    });
    this.scene.load.spritesheet("star_working", `${base}star-working-spritesheet-grid${supportsWebP ? ".webp" : ".png"}`, {
      frameWidth: 230, frameHeight: 144,
    });
    this.scene.load.image("sofa_idle", `${base}sofa-idle${ext("sofa-idle.png")}`);
    this.scene.load.spritesheet("sofa_busy", `${base}sofa-busy-spritesheet${ext("sofa-busy-spritesheet.png")}`, {
      frameWidth: 256, frameHeight: 256,
    });
    this.scene.load.spritesheet("cats", `${base}cats-spritesheet${supportsWebP ? ".webp" : ".png"}`, {
      frameWidth: 160, frameHeight: 160,
    });
    this.scene.load.spritesheet("plants", `${base}plants-spritesheet${ext("plants-spritesheet.png")}`, {
      frameWidth: 160, frameHeight: 160,
    });
    this.scene.load.spritesheet("posters", `${base}posters-spritesheet${ext("posters-spritesheet.png")}`, {
      frameWidth: 160, frameHeight: 160,
    });
    this.scene.load.spritesheet("serverroom", `${base}serverroom-spritesheet${ext("serverroom-spritesheet.png")}`, {
      frameWidth: 180, frameHeight: 251,
    });
    this.scene.load.spritesheet("sync_anim", `${base}sync-animation-spritesheet-grid${supportsWebP ? ".webp" : ".png"}`, {
      frameWidth: 256, frameHeight: 256,
    });
    this.scene.load.spritesheet("error_bug", `${base}error-bug-spritesheet-grid${supportsWebP ? ".webp" : ".png"}`, {
      frameWidth: 180, frameHeight: 180,
    });
    this.scene.load.image("desk_v2", `${base}desk-v2.png`);
    this.scene.load.spritesheet("flowers", `${base}flowers-spritesheet${supportsWebP ? ".webp" : ".png"}`, {
      frameWidth: 128, frameHeight: 128,
    });
    this.scene.load.spritesheet("coffee_machine", `${base}coffee-machine-spritesheet${ext("coffee-machine-spritesheet.png")}`, {
      frameWidth: 230, frameHeight: 230,
    });

    // Guest role sprites for agent avatars
    for (let i = 1; i <= 6; i++) {
      this.scene.load.image(`guest_role_${i}`, `${base}guest_role_${i}.png`);
    }

    // Petdex pets
    const pets = ["boba", "eve", "mallow", "nickel-file-ledger", "noir-webling"];
    for (const pet of pets) {
      this.scene.load.image(`petdex_${pet}`, `${base}petdex_${pet}.png`);
    }
  }

  // ── Create ───────────────────────────────────────────────

  createWorld() {
    const s = this.scene;
    const L = OFFICE_LAYOUT;

    // Background
    s.add.image(640, 360, "office_bg");

    // Animations
    createAnim(s, "star_idle", "star_idle", 0, 29, 12);
    createAnim(s, "star_working", "star_working", 0, 191, 12);
    createAnim(s, "serverroom_on", "serverroom", 0, 39, 6);
    createAnim(s, "error_bug_anim", "error_bug", 0, 95, 12);
    createAnim(s, "sync_anim_play", "sync_anim", 1, 48, 12);
    createAnim(s, "coffee_machine_anim", "coffee_machine", 0, 95, 12.5);
    createAnim(s, "sofa_busy_anim", "sofa_busy", 0, 0, 12);

    // Sofa
    this.sofa = s.add
      .sprite(L.furniture.sofa.x, L.furniture.sofa.y, "sofa_busy")
      .setOrigin(L.furniture.sofa.origin.x, L.furniture.sofa.origin.y)
      .setDepth(L.furniture.sofa.depth);
    this.sofa.anims.play("sofa_busy_anim");

    // Plants
    for (const p of L.furniture.plants) {
      const frame = Math.floor(Math.random() * 16);
      s.add.sprite(p.x, p.y, "plants", frame).setOrigin(0.5).setDepth(p.depth);
    }

    // Poster
    const posterFrame = Math.floor(Math.random() * 32);
    s.add.sprite(L.furniture.poster.x, L.furniture.poster.y, "posters", posterFrame)
      .setOrigin(0.5).setDepth(L.furniture.poster.depth);

    // Cat
    const catFrame = Math.floor(Math.random() * 16);
    s.add.sprite(L.furniture.cat.x, L.furniture.cat.y, "cats", catFrame)
      .setOrigin(L.furniture.cat.origin.x, L.furniture.cat.origin.y)
      .setDepth(L.furniture.cat.depth);

    // Coffee machine
    const cm = s.add
      .sprite(L.furniture.coffeeMachine.x, L.furniture.coffeeMachine.y, "coffee_machine")
      .setOrigin(L.furniture.coffeeMachine.origin.x, L.furniture.coffeeMachine.origin.y)
      .setDepth(L.furniture.coffeeMachine.depth);
    cm.anims.play("coffee_machine_anim");

    // Server room
    this.serverroom = s.add
      .sprite(L.furniture.serverroom.x, L.furniture.serverroom.y, "serverroom", 0)
      .setOrigin(L.furniture.serverroom.origin.x, L.furniture.serverroom.origin.y)
      .setDepth(L.furniture.serverroom.depth);
    this.serverroom.anims.stop();

    // Desk
    s.add.image(L.furniture.desk.x, L.furniture.desk.y, "desk_v2")
      .setOrigin(L.furniture.desk.origin.x, L.furniture.desk.origin.y)
      .setDepth(L.furniture.desk.depth);

    // Flower
    const flowerFrame = Math.floor(Math.random() * 16);
    s.add.sprite(L.furniture.flower.x, L.furniture.flower.y, "flowers", flowerFrame)
      .setOrigin(L.furniture.flower.origin.x, L.furniture.flower.origin.y)
      .setScale(L.furniture.flower.scale)
      .setDepth(L.furniture.flower.depth);

    // Error bug (hidden by default)
    this.errorBug = s.add
      .sprite(L.furniture.errorBug.x, L.furniture.errorBug.y, "error_bug", 0)
      .setOrigin(L.furniture.errorBug.origin.x, L.furniture.errorBug.origin.y)
      .setDepth(L.furniture.errorBug.depth)
      .setScale(L.furniture.errorBug.scale);
    this.errorBug.setVisible(false);
    this.errorBug.anims.play("error_bug_anim");

    // Star working (hidden by default)
    this.starWorking = s.add
      .sprite(L.furniture.starWorking.x, L.furniture.starWorking.y, "star_working", 0)
      .setOrigin(L.furniture.starWorking.origin.x, L.furniture.starWorking.origin.y)
      .setScale(L.furniture.starWorking.scale)
      .setDepth(L.furniture.starWorking.depth);
    this.starWorking.setVisible(false);

    // Sync animation (hidden by default)
    this.syncAnim = s.add
      .sprite(L.furniture.syncAnim.x, L.furniture.syncAnim.y, "sync_anim", 0)
      .setOrigin(L.furniture.syncAnim.origin.x, L.furniture.syncAnim.origin.y)
      .setDepth(L.furniture.syncAnim.depth);
    this.syncAnim.anims.stop();
    this.syncAnim.setFrame(0);
  }

  // ── Update (game loop) ───────────────────────────────────

  update(time: number) {
    // FPS tracking
    this.frameCount++;
    if (time - this.lastFpsTime >= 1000) {
      this.currentFps = Math.round(this.frameCount / ((time - this.lastFpsTime) / 1000));
      this.frameCount = 0;
      this.lastFpsTime = time;
    }

    // Server room animation based on agent activity
    if (this.pool.activeCount > 0) {
      if (!this.serverroom?.anims?.isPlaying) {
        this.serverroom?.anims?.play?.("serverroom_on");
      }
    } else {
      this.serverroom?.anims?.stop?.();
      this.serverroom?.setFrame?.(0);
    }

    // Zone-based culling: release agents outside current floor's Y range
    this.cullOffFloorAgents();
  }

  // ── Agent sync (called from Pinia bridge) ────────────────

  syncAgents(bots: Bot[]) {
    // Group bots by floor
    const floorBots = new Map<FloorId, Bot[]>();
    for (const fid of Object.keys(FLOOR_CONFIG) as FloorId[]) {
      floorBots.set(fid, []);
    }
    for (const bot of bots) {
      const floor = (bot.floor || "2F") as FloorId;
      floorBots.get(floor)?.push(bot);
    }

    // Assign zone positions
    this.agentZones.clear();
    for (const [fid, botList] of floorBots) {
      const zoneIndex = FLOOR_ZONE_MAP[fid] ?? 1;
      botList.forEach((bot, idx) => {
        this.agentZones.set(bot.id, { zoneIndex, index: idx });
      });
    }

    // Render agents on current floor
    const currentFloorBots = floorBots.get(this.currentFloor) || [];

    // Calculate total per zone for stable position computation
    const zoneTotals = new Map<number, number>();
    for (const [, { zoneIndex }] of this.agentZones) {
      zoneTotals.set(zoneIndex, (zoneTotals.get(zoneIndex) || 0) + 1);
    }

    // Release agents no longer in the bot list (removed offline agents)
    const currentBotIds = new Set(bots.map((b) => b.id));
    this.pool.forEach((_entry, agentId) => {
      if (!currentBotIds.has(agentId)) {
        this.pool.release(agentId);
      }
    });

    // Render each agent on the current floor
    for (const bot of currentFloorBots) {
      const zoneInfo = this.agentZones.get(bot.id);
      if (!zoneInfo) continue;

      const totalInZone = zoneTotals.get(zoneInfo.zoneIndex) || 1;
      const pos = computeStableAgentPosition(
        zoneInfo.zoneIndex,
        zoneInfo.index,
        totalInZone
      );

      this.pool.updateAgent(bot.id, bot, pos);
    }

    // Release agents that are now on other floors
    this.cullOffFloorAgents();
  }

  // ── Floor switching ──────────────────────────────────────

  setFloor(floor: FloorId) {
    this.currentFloor = floor;
    // Release all agents — they will be re-acquired on next syncAgents
    this.pool.releaseAll();
  }

  // ── Viewport culling ─────────────────────────────────────

  private cullOffFloorAgents() {
    const yRange = FLOOR_Y_RANGES[this.currentFloor];
    if (!yRange) return;

    const margin = 60; // Soft margin for smoother transitions
    const minY = yRange.min - margin;
    const maxY = yRange.max + margin;

    this.pool.forEach((entry, agentId) => {
      const y = entry.container.y;
      if (y < minY || y > maxY) {
        this.pool.release(agentId);
      }
    });
  }

  // ── Stats ────────────────────────────────────────────────

  getStats() {
    return {
      activeAgents: this.pool.activeCount,
      poolSize: this.pool.poolSize,
      fps: this.currentFps,
    };
  }

  resize(_width: number, _height: number) {
    // Phaser scale manager handles resize via ResizeObserver in PhaserCanvas.vue
    // This method exists to satisfy the SceneManagerAPI interface
  }

  getGame(): Phaser.Game {
    return this.game;
  }
}

// ═══════════════════════════════════════════════════════════════
// Scene factory — creates the Phaser scene config object
// ═══════════════════════════════════════════════════════════════

let managerInstance: SceneManager | null = null;

export function createOfficeScene(): {
  sceneConfig: any;
  getManager: () => SceneManager;
} {
  const manager = new SceneManager();
  managerInstance = manager;

  const sceneConfig = {
    key: "OfficeScene",
    preload: async function (this: any) {
      const webp = await detectWebP();
      manager.init(this, (this as any).game, webp);
      manager.preloadAssets(webp);
    },
    create: function (this: any) {
      manager.createWorld();
    },
    update: function (this: any, time: number) {
      manager.update(time);
    },
  };

  return {
    sceneConfig,
    getManager: () => manager,
  };
}

export function getSceneManager(): SceneManager | null {
  return managerInstance;
}

// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

function createAnim(
  scene: any,
  key: string,
  textureKey: string,
  start: number,
  end: number,
  frameRate: number
) {
  try {
    scene.anims.create({
      key,
      frames: scene.anims.generateFrameNumbers(textureKey, { start, end }),
      frameRate,
      repeat: -1,
    });
  } catch {
    // Animation may already exist (scene restart), ignore
  }
}