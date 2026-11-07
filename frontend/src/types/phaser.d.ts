/**
 * Minimal Phaser 3.80 type declarations for TypeScript compilation.
 * The actual Phaser library is loaded via <script> tag in index.html.
 * Extends the existing declarations with Scene types needed for OfficeScene.
 */

declare namespace Phaser {
  const AUTO: number;

  class Game {
    constructor(config?: Phaser.Types.Core.GameConfig);
    destroy(removeCanvas?: boolean): void;
    scale: Scale.ScaleManager;
    scene: Scene.SceneManager;
  }

  namespace Scale {
    const FIT: number;
    const CENTER_BOTH: number;

    class ScaleManager {
      resize(width: number, height: number): void;
    }
  }

  namespace Scene {
    class SceneManager {
      getScene(key: string): Scene | null;
    }

    class Scene {
      add: GameObjects.GameObjectFactory;
      load: Loader.LoaderPlugin;
      anims: Animations.AnimationManager;
      input: Input.InputPlugin;
      physics: Physics.Arcade.ArcadePhysics;
      game: Game;
      scene: SceneManager;
      cameras: Cameras.Scene2D.CameraManager;
      textures: Textures.TextureManager;

      constructor(config: string | Types.Scenes.SettingsConfig);
    }
  }

  namespace GameObjects {
    class GameObjectFactory {
      image(x: number, y: number, texture: string, frame?: number): GameObjects.Image;
      sprite(x: number, y: number, texture: string, frame?: number): GameObjects.Sprite;
      text(x: number, y: number, text: string, style?: any): GameObjects.Text;
      rectangle(x: number, y: number, width: number, height: number, fillColor?: number, fillAlpha?: number): GameObjects.Rectangle;
      circle(x: number, y: number, radius: number, fillColor?: number, fillAlpha?: number): GameObjects.Arc;
      container(x: number, y: number, children?: any[]): GameObjects.Container;
    }

    class GameObject {
      x: number;
      y: number;
      width: number;
      height: number;
      visible: boolean;
      active: boolean;
      alpha: number;
      depth: number;
      scale: number;
      name: string;
      type: string;

      setPosition(x: number, y: number, z?: number, w?: number): this;
      setOrigin(x: number, y?: number): this;
      setScale(x: number, y?: number): this;
      setAlpha(value: number): this;
      setDepth(value: number): this;
      setVisible(value: boolean): this;
      setActive(value: boolean): this;
      setFrame(frame: number): this;
      setTexture(key: string, frame?: number): this;
      setInteractive(config?: any): this;
      destroy(fromScene?: boolean): void;
      on(event: string, fn: Function, context?: any): this;
      getAt(index: number): any;
    }

    class Image extends GameObject {
      texture: { key: string };
    }

    class Sprite extends GameObject {
      anims: any;
      texture: { key: string };
    }

    class Text extends GameObject {
      text: string;
      setText(value: string): this;
      setColor(value: string): this;
      setFill(value: string): this;
      setFontFamily(value: string): this;
      setFontSize(value: number | string): this;
    }

    class Rectangle extends GameObject {
      fillColor: number;
      fillAlpha: number;
      setStrokeStyle(width: number, color: number, alpha?: number): this;
    }

    class Arc extends GameObject {
      fillColor: number;
      setFillStyle(color: number, alpha?: number): this;
      setStrokeStyle(width: number, color: number, alpha?: number): this;
    }

    class Container extends GameObject {
      add(child: any | any[]): this;
      remove(child: any, destroyChild?: boolean): this;
      removeAll(destroyChild?: boolean): this;
      getAt(index: number): any;
      getAll(): any[];
      length: number;
    }
  }

  namespace Loader {
    interface LoaderPlugin {
      image(key: string, url: string): void;
      spritesheet(key: string, url: string, config: { frameWidth: number; frameHeight: number }): void;
      on(event: string, callback: Function, context?: any): void;
    }
  }

  namespace Animations {
    interface AnimationManager {
      create(config: {
        key: string;
        frames: any[];
        frameRate: number;
        repeat: number;
      }): any;
      generateFrameNumbers(key: string, config: { start: number; end: number }): any[];
      play(key: string, ignoreIfPlaying?: boolean): any;
    }
  }

  namespace Input {
    interface InputPlugin {
      on(event: string, callback: Function, context?: any): void;
    }
  }

  namespace Physics {
    namespace Arcade {
      interface ArcadePhysics {
        add: {
          sprite(x: number, y: number, texture: string, frame?: number): GameObjects.Sprite;
        };
      }
    }
  }

  namespace Cameras {
    namespace Scene2D {
      interface CameraManager {
        main: Cameras.Scene2D.Camera;
      }
    }
  }

  namespace Textures {
    interface TextureManager {
      exists(key: string): boolean;
    }
  }

  namespace Types {
    namespace Core {
      interface GameConfig {
        type?: number;
        width?: number;
        height?: number;
        parent?: string | HTMLElement;
        pixelArt?: boolean;
        backgroundColor?: string;
        physics?: {
          default?: string;
          arcade?: {
            gravity?: { x?: number; y?: number };
            debug?: boolean;
          };
        };
        scale?: {
          mode?: number;
          autoCenter?: number;
          width?: number;
          height?: number;
        };
        scene?: any;
      }
    }

    namespace Scenes {
      interface SettingsConfig {
        key?: string;
        active?: boolean;
        visible?: boolean;
      }
    }
  }

  namespace Cameras {
    namespace Scene2D {
      class Camera {
        scrollX: number;
        scrollY: number;
        width: number;
        height: number;
        setBounds(x: number, y: number, width: number, height: number): this;
      }
    }
  }
}