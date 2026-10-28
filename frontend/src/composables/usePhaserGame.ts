import { onBeforeUnmount, type Ref } from "vue";

/**
 * Bridge to the existing Phaser game (game.js / layout.js).
 * Mounts the Phaser canvas inside the provided container element.
 * Ensures Phaser rendering and Vue UI layer don't conflict.
 */
export function usePhaserGame(container: Ref<HTMLElement>) {
  let game: Phaser.Game | null = null;
  let resizeObserver: ResizeObserver | null = null;

  async function boot() {
    if (!container.value) return;

    // Dynamically load layout.js and game.js if not already loaded
    const scripts = document.querySelectorAll(
      'script[src$="layout.js"], script[src$="game.js"]'
    );

    if (scripts.length < 2) {
      await loadScript("/static/layout.js");
      await loadScript("/static/game.js");
    }

    // The game.js auto-creates the Phaser instance into #game-container
    // Vue just provides the container element
    resizeObserver = new ResizeObserver(() => {
      game?.scale?.resize(container.value!.clientWidth, container.value!.clientHeight);
    });
    resizeObserver.observe(container.value);
  }

  function loadScript(src: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.appendChild(s);
    });
  }

  boot();

  onBeforeUnmount(() => {
    resizeObserver?.disconnect();
    game?.destroy(true);
    game = null;
  });

  return { game };
}
