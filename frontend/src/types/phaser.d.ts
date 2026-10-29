declare namespace Phaser {
  class Game {
    constructor(config: Phaser.Types.Core.GameConfig);
    destroy(removeCanvas?: boolean): void;
    scale: Scale.ScaleManager;
  }
  namespace Scale {
    class ScaleManager {
      resize(width: number, height: number): void;
    }
  }
  namespace Types {
    namespace Core {
      interface GameConfig {
        type?: number;
        width?: number;
        height?: number;
        parent?: string;
        pixelArt?: boolean;
        physics?: { default: string; arcade: { gravity: { y: number }; debug: boolean } };
        scene: any;
      }
    }
  }
  const AUTO: number;
}
