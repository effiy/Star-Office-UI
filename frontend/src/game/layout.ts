/**
 * Office Layout Configuration — extracted from layout.js as ESM module
 * All coordinates, depth values, and resource paths centralized here.
 */

export const OFFICE_LAYOUT = {
  game: {
    width: 1280,
    height: 720,
  },

  areas: {
    door: { x: 640, y: 550 },
    writing: { x: 320, y: 360 },
    researching: { x: 320, y: 360 },
    error: { x: 1066, y: 180 },
    breakroom: { x: 640, y: 360 },
  },

  furniture: {
    sofa: { x: 670, y: 144, origin: { x: 0, y: 0 }, depth: 10 },
    desk: { x: 218, y: 417, origin: { x: 0.5, y: 0.5 }, depth: 1000 },
    flower: { x: 310, y: 390, origin: { x: 0.5, y: 0.5 }, depth: 1100, scale: 0.8 },
    starWorking: { x: 217, y: 333, origin: { x: 0.5, y: 0.5 }, depth: 900, scale: 1.32 },
    plants: [
      { x: 565, y: 178, depth: 5 },
      { x: 230, y: 185, depth: 5 },
      { x: 977, y: 496, depth: 5 },
    ],
    poster: { x: 252, y: 66, depth: 4 },
    coffeeMachine: { x: 659, y: 397, origin: { x: 0.5, y: 0.5 }, depth: 99 },
    serverroom: { x: 1021, y: 142, origin: { x: 0.5, y: 0.5 }, depth: 2 },
    errorBug: {
      x: 1007, y: 221, origin: { x: 0.5, y: 0.5 }, depth: 50, scale: 0.9,
      pingPong: { leftX: 1007, rightX: 1111, speed: 0.6 },
    },
    syncAnim: { x: 1157, y: 592, origin: { x: 0.5, y: 0.5 }, depth: 40 },
    cat: { x: 94, y: 557, origin: { x: 0.5, y: 0.5 }, depth: 2000 },
  },

  plaque: { x: 640, y: 720 - 36, width: 420, height: 44 },

  forcePng: { desk_v2: true },
  totalAssets: 15,
} as const;

/**
 * Agent position allocator — generates unique positions within office zones.
 * Supports up to 50 agents per zone via grid+spiral allocation.
 */
export interface PositionAllocator {
  area: string;
  baseX: number;
  baseY: number;
  rangeX: number;
  rangeY: number;
  slots: number;
}

export const AGENT_ZONES: PositionAllocator[] = [
  // 1F — Management decision layer (top area)
  { area: "breakroom", baseX: 640, baseY: 120, rangeX: 220, rangeY: 100, slots: 15 },
  // 2F — Engineering execution layer (middle area)  
  { area: "writing", baseX: 320, baseY: 340, rangeX: 280, rangeY: 140, slots: 20 },
  // 3F — Creative content layer (bottom area)
  { area: "breakroom", baseX: 960, baseY: 540, rangeX: 220, rangeY: 120, slots: 15 },
];

/**
 * Compute agent position based on zone, agent index, and total count.
 * Uses a grid-layout algorithm to prevent overlap at high agent counts.
 */
export function computeAgentPosition(
  zoneIndex: number,
  agentIndex: number,
  totalInZone: number
): { x: number; y: number } {
  const zone = AGENT_ZONES[zoneIndex % AGENT_ZONES.length];
  if (!zone || totalInZone <= 0) return { x: 400, y: 360 };

  // Grid layout: fit agents into a roughly rectangular grid within the zone
  const cols = Math.min(totalInZone, Math.ceil(Math.sqrt(totalInZone * 2)));
  const rows = Math.ceil(totalInZone / cols);
  const col = agentIndex % cols;
  const row = Math.floor(agentIndex / cols);

  const cellW = zone.rangeX / Math.max(cols, 1);
  const cellH = zone.rangeY / Math.max(rows, 1);

  // Add slight random jitter to avoid looking too grid-like
  const jitterX = (Math.random() - 0.5) * cellW * 0.3;
  const jitterY = (Math.random() - 0.5) * cellH * 0.3;

  return {
    x: zone.baseX - zone.rangeX / 2 + cellW * (col + 0.5) + jitterX,
    y: zone.baseY - zone.rangeY / 2 + cellH * (row + 0.5) + jitterY,
  };
}

/**
 * Deterministic position — no jitter, for stable agent positions across renders
 */
export function computeStableAgentPosition(
  zoneIndex: number,
  agentIndex: number,
  totalInZone: number
): { x: number; y: number } {
  const zone = AGENT_ZONES[zoneIndex % AGENT_ZONES.length];
  if (!zone || totalInZone <= 0) return { x: 400, y: 360 };

  const cols = Math.min(totalInZone, Math.ceil(Math.sqrt(totalInZone * 2)));
  const rows = Math.ceil(totalInZone / cols);
  const col = agentIndex % cols;
  const row = Math.floor(agentIndex / cols);

  const cellW = zone.rangeX / Math.max(cols, 1);
  const cellH = zone.rangeY / Math.max(rows, 1);

  return {
    x: zone.baseX - zone.rangeX / 2 + cellW * (col + 0.5),
    y: zone.baseY - zone.rangeY / 2 + cellH * (row + 0.5),
  };
}