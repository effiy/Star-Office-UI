/**
 * EffectLayer — renders particle effects and environmental overlays
 *
 * Manages:
 * - Ambient particles (dust motes)
 * - Floor transition effects
 * - Error / syncing glow overlays
 * - Rain/night mode (future)
 */

export interface EffectLayerAPI {
  /** Initialize the layer with the Phaser scene */
  init(scene: any): void;
  /** Show a floor transition overlay */
  playFloorTransition(from: string, to: string): void;
  /** Show error glow effect */
  showErrorGlow(x: number, y: number): void;
  /** Show syncing particles */
  showSyncParticles(x: number, y: number): void;
  /** Update animations (called in game loop) */
  update(_time: number, _delta: number): void;
  /** Clear all active effects */
  clear(): void;
}

export function createEffectLayer(): EffectLayerAPI {
  let scene: any = null;
  const activeEffects: any[] = [];

  function init(s: any) {
    scene = s;
  }

  function playFloorTransition(_from: string, _to: string) {
    if (!scene) return;
    // Simple fade overlay
    const overlay = scene.add.rectangle(640, 360, 1280, 720, 0x000000, 0);
    overlay.setDepth(5000);

    // Fade in → out
    scene.tweens?.add?.({
      targets: overlay,
      alpha: 0.3,
      duration: 150,
      yoyo: true,
      onComplete: () => overlay.destroy(),
    });

    // If tweens not available, just fade manually
    if (!scene.tweens) {
      let alpha = 0;
      const step = () => {
        alpha += 0.05;
        overlay.alpha = Math.min(alpha, 0.3);
        if (alpha < 0.3) {
          requestAnimationFrame(() => {
            step();
          });
        } else {
          setTimeout(() => overlay.destroy(), 200);
        }
      };
      step();
    }
  }

  function showErrorGlow(x: number, y: number) {
    if (!scene) return;
    const glow = scene.add.circle(x, y, 40, 0xef4444, 0.15);
    glow.setDepth(4900);
    activeEffects.push(glow);

    if (scene.tweens?.add) {
      scene.tweens.add({
        targets: glow,
        scaleX: 1.5,
        scaleY: 1.5,
        alpha: 0,
        duration: 800,
        onComplete: () => {
          glow.destroy();
          const idx = activeEffects.indexOf(glow);
          if (idx >= 0) activeEffects.splice(idx, 1);
        },
      });
    } else {
      setTimeout(() => {
        glow.destroy();
        const idx = activeEffects.indexOf(glow);
        if (idx >= 0) activeEffects.splice(idx, 1);
      }, 800);
    }
  }

  function showSyncParticles(x: number, y: number) {
    if (!scene) return;
    // Simple rotating dots
    for (let i = 0; i < 4; i++) {
      const angle = (i / 4) * Math.PI * 2;
      const dot = scene.add.circle(
        x + Math.cos(angle) * 30,
        y + Math.sin(angle) * 30,
        4,
        0x22c55e,
        0.6
      );
      dot.setDepth(4900);
      activeEffects.push(dot);

      if (scene.tweens?.add) {
        scene.tweens.add({
          targets: dot,
          alpha: 0,
          scaleX: 0.1,
          scaleY: 0.1,
          duration: 1200,
          onComplete: () => {
            dot.destroy();
            const idx = activeEffects.indexOf(dot);
            if (idx >= 0) activeEffects.splice(idx, 1);
          },
        });
      } else {
        setTimeout(() => {
          dot.destroy();
          const idx = activeEffects.indexOf(dot);
          if (idx >= 0) activeEffects.splice(idx, 1);
        }, 1200);
      }
    }
  }

  function update(_time: number, _delta: number) {
    // Reserved for continuous effects (rain, particles)
  }

  function clear() {
    for (const fx of activeEffects) {
      try { fx.destroy(); } catch { /* ignore */ }
    }
    activeEffects.length = 0;
  }

  return { init, playFloorTransition, showErrorGlow, showSyncParticles, update, clear };
}