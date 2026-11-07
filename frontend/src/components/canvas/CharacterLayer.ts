/**
 * CharacterLayer — renders agent character sprites in the office
 *
 * Layers on top of MapLayer; manages:
 * - Agent sprite rendering via AgentPool
 * - Bubble text popups
 * - Walking animations (future)
 * - Status indicators
 */

import { AgentPool } from "../../game/AgentPool";
import { computeStableAgentPosition, AGENT_ZONES } from "../../game/layout";
import type { Bot, FloorId } from "../../stores/useBotStore";
import { FLOOR_CONFIG } from "../../stores/useBotStore";

export interface CharacterLayerAPI {
  /** Set up the layer with an AgentPool */
  init(scene: any, pool: AgentPool): void;
  /** Sync bot data from store into sprites */
  syncAgents(bots: Bot[], currentFloor: FloorId): void;
  /** Dispatch all agents visible on the current floor */
  cullOffFloor(currentFloor: FloorId): void;
  /** Show a bubble over an agent */
  showBubble(agentId: string, text: string, durationMs?: number): void;
}

export function createCharacterLayer(): CharacterLayerAPI {
  let pool: AgentPool | null = null;
  let scene: any = null;

  // Zone-to-floor mapping
  const FLOOR_ZONE_MAP: Record<string, number> = {
    "1F": 0, "2F": 1, "3F": 2,
  };

  const FLOOR_Y_RANGES: Record<string, { min: number; max: number }> = {
    "1F": { min: 40, max: 240 },
    "2F": { min: 260, max: 480 },
    "3F": { min: 500, max: 696 },
  };

  // Track zone assignments for stable positioning
  const agentZones = new Map<string, { zoneIndex: number; index: number }>();

  function init(s: any, p: AgentPool) {
    scene = s;
    pool = p;
  }

  function syncAgents(bots: Bot[], currentFloor: FloorId) {
    if (!pool) return;

    // Group bots by floor
    const floorBots = new Map<string, Bot[]>();
    for (const fid of Object.keys(FLOOR_CONFIG)) {
      floorBots.set(fid, []);
    }
    for (const bot of bots) {
      const floor = bot.floor || "2F";
      if (!floorBots.has(floor)) floorBots.set(floor, []);
      floorBots.get(floor)!.push(bot);
    }

    // Assign zone positions
    agentZones.clear();
    for (const [fid, botList] of floorBots) {
      const zoneIndex = FLOOR_ZONE_MAP[fid] ?? 1;
      botList.forEach((bot, idx) => {
        agentZones.set(bot.id, { zoneIndex, index: idx });
      });
    }

    // Remove agents no longer in the list
    const currentIds = new Set(bots.map((b) => b.id));
    pool.forEach((_entry, agentId) => {
      if (!currentIds.has(agentId)) {
        pool!.release(agentId);
      }
    });

    // Calculate totals per zone
    const zoneTotals = new Map<number, number>();
    for (const [, { zoneIndex }] of agentZones) {
      zoneTotals.set(zoneIndex, (zoneTotals.get(zoneIndex) || 0) + 1);
    }

    // Render each agent on the current floor
    const onFloor = floorBots.get(currentFloor) || [];
    for (const bot of onFloor) {
      const zoneInfo = agentZones.get(bot.id);
      if (!zoneInfo) continue;

      const total = zoneTotals.get(zoneInfo.zoneIndex) || 1;
      const pos = computeStableAgentPosition(zoneInfo.zoneIndex, zoneInfo.index, total);
      pool.updateAgent(bot.id, bot, pos);
    }

    // Cull agents on other floors
    cullOffFloor(currentFloor);
  }

  function cullOffFloor(currentFloor: FloorId) {
    if (!pool) return;
    const yRange = FLOOR_Y_RANGES[currentFloor];
    if (!yRange) return;

    const margin = 60;
    const minY = yRange.min - margin;
    const maxY = yRange.max + margin;

    pool.forEach((entry, agentId) => {
      if (entry.container.y < minY || entry.container.y > maxY) {
        pool!.release(agentId);
      }
    });
  }

  function showBubble(agentId: string, text: string, durationMs = 3000) {
    if (!pool || !scene) return;
    const entry = pool.get(agentId);
    if (!entry) return;

    const x = entry.container.x;
    const y = entry.container.y - 70;

    const bg = scene.add.rectangle(x, y, text.length * 10 + 20, 28, 0xffffff, 0.95);
    bg.setStrokeStyle(2, 0x000000);
    const txt = scene.add.text(x, y, text, {
      fontFamily: "ArkPixel, monospace",
      fontSize: "12px",
      fill: "#000",
      align: "center",
    }).setOrigin(0.5);

    const bubble = scene.add.container(0, 0, [bg, txt]);
    bubble.setDepth(9999);

    setTimeout(() => {
      try { bubble.destroy(); } catch { /* already gone */ }
    }, durationMs);
  }

  return { init, syncAgents, cullOffFloor, showBubble };
}