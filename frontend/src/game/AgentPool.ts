/**
 * AgentPool — Object Pool for agent sprite containers
 * SU-04: Extends agent capacity from 16 → ≤50 via reuse pattern
 *
 * - Pre-allocates containers lazily (up to maxSize)
 * - acquire/release lifecycle instead of create/destroy
 * - Tracks active agents for efficient iteration
 * - Automatic pool growth when exhausted (within max)
 */

import type { Bot } from "../stores/useBotStore";

export interface AgentPoolEntry {
  container: any; // Phaser.GameObjects.Container
  agentId: string;
  nameTag: any; // Phaser.GameObjects.Text
  statusDot: any; // Phaser.GameObjects.Arc
  body: any; // Phaser.GameObjects.Sprite | Phaser.GameObjects.Text
}

export class AgentPool {
  private scene: any; // Phaser.Scene
  private available: AgentPoolEntry[] = [];
  private active: Map<string, AgentPoolEntry> = new Map();
  private maxSize: number;
  private createdCount = 0;

  constructor(scene: any, maxSize = 50) {
    this.scene = scene;
    this.maxSize = maxSize;
  }

  /** Grab a container from the pool (or create a new one if within limits) */
  acquire(agentId: string): AgentPoolEntry | undefined {
    // Already active? Return existing
    const existing = this.active.get(agentId);
    if (existing) return existing;

    let entry: AgentPoolEntry;

    if (this.available.length > 0) {
      entry = this.available.pop()!;
      entry.agentId = agentId;
    } else if (this.createdCount < this.maxSize) {
      entry = this.createContainer();
      entry.agentId = agentId;
      this.createdCount++;
    } else {
      // Pool exhausted — recycle the oldest active agent (LRU eviction)
      console.warn(`[AgentPool] Pool exhausted (${this.maxSize}), evicting oldest agent`);
      const oldest = this.active.entries().next().value;
      if (oldest) {
        this.release(oldest[0]);
        entry = this.available.pop()!;
        entry.agentId = agentId;
      } else {
        return undefined;
      }
    }

    entry.container.setVisible(true);
    entry.container.setActive(true);
    this.active.set(agentId, entry);
    return entry;
  }

  /** Release a container back to the pool */
  release(agentId: string): void {
    const entry = this.active.get(agentId);
    if (!entry) return;

    entry.container.setVisible(false);
    entry.container.setActive(false);
    entry.container.setPosition(-1000, -1000); // Move off-screen
    this.active.delete(agentId);
    this.available.push(entry);
  }

  /** Release all active agents back to pool */
  releaseAll(): void {
    for (const [id] of this.active) {
      this.release(id);
    }
  }

  /** Get an active entry by agent ID */
  get(agentId: string): AgentPoolEntry | undefined {
    return this.active.get(agentId);
  }

  /** Check if an agent is currently active */
  isActive(agentId: string): boolean {
    return this.active.has(agentId);
  }

  /** Update an agent's visual state (name, color, position) */
  updateAgent(agentId: string, bot: Bot, position: { x: number; y: number }): void {
    let entry = this.active.get(agentId);

    if (!entry) {
      entry = this.acquire(agentId);
      if (!entry) return;
    }

    entry.container.setPosition(position.x, position.y);
    entry.container.setAlpha(this.getAlpha(bot));
    entry.container.setDepth(this.getDepth(bot));

    // Update name tag
    entry.nameTag.setText(bot.name);
    entry.nameTag.setColor(this.getNameColor(bot));

    // Update status dot
    entry.statusDot.setFillStyle(this.getDotColor(bot));

    // Update avatar sprite (if body is a sprite with texture support)
    if (entry.body && typeof entry.body.setTexture === "function") {
      const avatarKey = this.getAvatarKey(bot);
      if (avatarKey && this.scene.textures.exists(avatarKey)) {
        if (entry.body.texture && entry.body.texture.key !== avatarKey) {
          entry.body.setTexture(avatarKey);
        }
      }
    }
  }

  get activeCount(): number {
    return this.active.size;
  }

  get poolSize(): number {
    return this.createdCount;
  }

  get isExhausted(): boolean {
    return this.active.size >= this.maxSize && this.available.length === 0;
  }

  /** Iterate over all active entries */
  forEach(callback: (entry: AgentPoolEntry, agentId: string) => void): void {
    this.active.forEach((entry, id) => callback(entry, id));
  }

  // ── Private helpers ──

  private createContainer(): AgentPoolEntry {
    const container = this.scene.add.container(-1000, -1000);
    container.setVisible(false);
    container.setActive(false);
    container.setDepth(1200);

    // Body sprite (placeholder — updated on acquire)
    const body = this.scene.add.text(0, 0, "🤖", {
      fontFamily: "ArkPixel, monospace",
      fontSize: "32px",
    }).setOrigin(0.5);
    (body as any).name = "body";

    // Name tag
    const nameTag = this.scene.add.text(0, -72, "", {
      fontFamily: "ArkPixel, monospace",
      fontSize: "14px",
      fill: "#64748b",
      stroke: "#000",
      strokeThickness: 3,
      backgroundColor: "rgba(255,255,255,0.95)",
    }).setOrigin(0.5);
    (nameTag as any).name = "nameTag";

    // Status dot
    const statusDot = this.scene.add.circle(70, -64, 5, 0x64748b, 1);
    statusDot.setStrokeStyle(2, 0x000000, 1);
    (statusDot as any).name = "statusDot";

    container.add([body, statusDot, nameTag]);

    return {
      container,
      agentId: "",
      nameTag,
      statusDot: statusDot as unknown as Phaser.GameObjects.Arc,
      body,
    };
  }

  private getAlpha(bot: Bot): number {
    // Alpha based on agent state relevance
    switch (bot.state) {
      case "error": return 0.85;
      case "idle": return 0.8;
      case "syncing": return 0.75;
      default: return 1;
    }
  }

  private getDepth(bot: Bot): number {
    // Higher depth for active agents, lower for idle
    switch (bot.state) {
      case "error": return 1300;
      case "executing": return 1250;
      case "writing":
      case "researching": return 1220;
      case "syncing": return 1210;
      case "idle":
      default: return 1200;
    }
  }

  private getNameColor(bot: Bot): string {
    switch (bot.state) {
      case "error": return "#ef4444";
      case "executing": return "#22c55e";
      case "writing":
      case "researching": return "#3b82f6";
      case "syncing": return "#f59e0b";
      case "idle":
      default: return "#64748b";
    }
  }

  private getDotColor(bot: Bot): number {
    switch (bot.state) {
      case "error": return 0xef4444;
      case "executing": return 0x22c55e;
      case "writing":
      case "researching": return 0x3b82f6;
      case "syncing": return 0xf59e0b;
      case "idle":
      default: return 0x64748b;
    }
  }

  private getAvatarKey(bot: Bot): string {
    if (bot.avatar && this.scene.textures.exists(bot.avatar)) {
      return bot.avatar;
    }
    // Fallback to deterministic guest role
    const hash = this.hashCode(bot.id);
    const key = `guest_role_${1 + (hash % 6)}`;
    return this.scene.textures.exists(key) ? key : "";
  }

  private hashCode(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash);
  }
}