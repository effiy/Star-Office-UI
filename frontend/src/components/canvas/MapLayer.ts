/**
 * MapLayer — renders the office floor background + decorative elements
 *
 * Manages:
 * - Background image (office_bg)
 * - Furniture (sofa, desk, plants, posters, coffee machine, server room, cat)
 * - Plaque (office name sign)
 *
 * This is a pure rendering layer; no game logic or input handling here.
 */

import { OFFICE_LAYOUT } from "../../game/layout";

export interface MapLayerAPI {
  /** Preload all map assets into the Phaser scene */
  preload(scene: any, supportsWebP: boolean): void;
  /** Create all map objects (called in scene.create) */
  create(scene: any): Record<string, any>;
  /** Update animations (called in scene.update) */
  update(_time: number, _delta: number): void;
}

export function createMapLayer(): MapLayerAPI {
  const refs: Record<string, any> = {};

  function preload(scene: any, supportsWebP: boolean) {
    const ext = (name: string) => {
      const key = name.replace(/\.(png|webp)$/, "");
      if ((OFFICE_LAYOUT.forcePng as any)[key]) return ".png";
      return supportsWebP ? ".webp" : ".png";
    };
    const base = "/static/";

    scene.load.image("office_bg", `${base}office_bg_small${supportsWebP ? ".webp" : ".png"}`);
    scene.load.spritesheet("cats", `${base}cats-spritesheet${supportsWebP ? ".webp" : ".png"}`, { frameWidth: 160, frameHeight: 160 });
    scene.load.spritesheet("plants", `${base}plants-spritesheet${ext("plants-spritesheet.png")}`, { frameWidth: 160, frameHeight: 160 });
    scene.load.spritesheet("posters", `${base}posters-spritesheet${ext("posters-spritesheet.png")}`, { frameWidth: 160, frameHeight: 160 });
    scene.load.spritesheet("serverroom", `${base}serverroom-spritesheet${ext("serverroom-spritesheet.png")}`, { frameWidth: 180, frameHeight: 251 });
    scene.load.spritesheet("coffee_machine", `${base}coffee-machine-spritesheet${ext("coffee-machine-spritesheet.png")}`, { frameWidth: 230, frameHeight: 230 });
    scene.load.image("sofa_idle", `${base}sofa-idle${ext("sofa-idle.png")}`);
    scene.load.spritesheet("sofa_busy", `${base}sofa-busy-spritesheet${ext("sofa-busy-spritesheet.png")}`, { frameWidth: 256, frameHeight: 256 });
    scene.load.image("desk_v2", `${base}desk-v2.png`);
    scene.load.spritesheet("flowers", `${base}flowers-spritesheet${supportsWebP ? ".webp" : ".png"}`, { frameWidth: 128, frameHeight: 128 });
  }

  function create(scene: any): Record<string, any> {
    const L = OFFICE_LAYOUT;

    // Background
    scene.add.image(640, 360, "office_bg");

    // Sofa
    _makeAnim(scene, "sofa_busy_anim", "sofa_busy", 0, 0, 12);
    refs.sofa = scene.add.sprite(L.furniture.sofa.x, L.furniture.sofa.y, "sofa_busy")
      .setOrigin(L.furniture.sofa.origin.x, L.furniture.sofa.origin.y)
      .setDepth(L.furniture.sofa.depth);
    refs.sofa.anims.play("sofa_busy_anim");

    // Plants
    for (const p of L.furniture.plants) {
      const frame = Math.floor(Math.random() * 16);
      scene.add.sprite(p.x, p.y, "plants", frame).setOrigin(0.5).setDepth(p.depth);
    }

    // Poster
    const posterFrame = Math.floor(Math.random() * 32);
    scene.add.sprite(L.furniture.poster.x, L.furniture.poster.y, "posters", posterFrame)
      .setOrigin(0.5).setDepth(L.furniture.poster.depth);

    // Cat
    const catFrame = Math.floor(Math.random() * 16);
    refs.cat = scene.add.sprite(L.furniture.cat.x, L.furniture.cat.y, "cats", catFrame)
      .setOrigin(L.furniture.cat.origin.x, L.furniture.cat.origin.y)
      .setDepth(L.furniture.cat.depth);

    // Coffee machine
    _makeAnim(scene, "coffee_machine_anim", "coffee_machine", 0, 95, 12.5);
    const cm = scene.add.sprite(L.furniture.coffeeMachine.x, L.furniture.coffeeMachine.y, "coffee_machine")
      .setOrigin(L.furniture.coffeeMachine.origin.x, L.furniture.coffeeMachine.origin.y)
      .setDepth(L.furniture.coffeeMachine.depth);
    cm.anims.play("coffee_machine_anim");

    // Server room
    _makeAnim(scene, "serverroom_on", "serverroom", 0, 39, 6);
    refs.serverroom = scene.add.sprite(L.furniture.serverroom.x, L.furniture.serverroom.y, "serverroom", 0)
      .setOrigin(L.furniture.serverroom.origin.x, L.furniture.serverroom.origin.y)
      .setDepth(L.furniture.serverroom.depth);
    refs.serverroom.anims.stop();

    // Desk
    scene.add.image(L.furniture.desk.x, L.furniture.desk.y, "desk_v2")
      .setOrigin(L.furniture.desk.origin.x, L.furniture.desk.origin.y)
      .setDepth(L.furniture.desk.depth);

    // Flower
    const flowerFrame = Math.floor(Math.random() * 16);
    scene.add.sprite(L.furniture.flower.x, L.furniture.flower.y, "flowers", flowerFrame)
      .setOrigin(L.furniture.flower.origin.x, L.furniture.flower.origin.y)
      .setScale(L.furniture.flower.scale)
      .setDepth(L.furniture.flower.depth);

    // Plaque
    const pl = L.plaque;
    scene.add.rectangle(pl.x, pl.y, pl.width, pl.height, 0x5d4037)
      .setStrokeStyle(3, 0x3e2723);
    scene.add.text(pl.x, pl.y, "像素办公室", {
      fontFamily: "ArkPixel, monospace",
      fontSize: "18px",
      fill: "#ffd700",
      fontWeight: "bold",
      stroke: "#000",
      strokeThickness: 2,
    }).setOrigin(0.5);

    return refs;
  }

  function update(_time: number, _delta: number) {
    // Map is static; reserved for future dynamic decorations
  }

  return { preload, create, update };
}

function _makeAnim(scene: any, key: string, tex: string, s: number, e: number, fps: number) {
  try {
    scene.anims.create({
      key,
      frames: scene.anims.generateFrameNumbers(tex, { start: s, end: e }),
      frameRate: fps,
      repeat: -1,
    });
  } catch { /* already exists */ }
}