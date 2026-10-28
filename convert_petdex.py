#!/usr/bin/env python3
"""
Petdex → Star-Office-UI 精灵转换器

将 Petdex v2 格式的 spritesheet 转换为 Star-Office-UI 可用的精灵文件。

用法:
  python3 convert_petdex.py <pet-slug> [--fw FRAME_WIDTH] [--fh FRAME_HEIGHT]
  
示例:
  python3 convert_petdex.py boba
  python3 convert_petdex.py boba --fw 128 --fh 176

Petdex 宠物安装位置: ~/.petdex/pets/<slug>/
Star-Office-UI 精灵目录: Star-Office-UI/frontend/static/

转换后会生成:
  - petdex_<slug>.png          # 第一帧（立绘，用于 office 显示）
  - petdex_<slug>_sheet.png    # 完整 spritesheet 副本
  - petdex_<slug>.json         # 元数据（帧尺寸、行列数）
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from PIL import Image

PETDEX_DIR = Path.home() / ".petdex" / "pets"
STAR_OFFICE_STATIC = Path(__file__).resolve().parent / "frontend"


def detect_frame_size(spritesheet_path: str) -> tuple:
    """自动检测 Petdex v2 spritesheet 的帧尺寸。
    
    Petdex v2 格式通常按以下规则:
    - 帧宽一般是 96, 128, 或 192 像素
    - 帧高一般是帧宽，或按比例 (9:16, 1:1 等)
    - 整个 spritesheet 是整齐的网格
    """
    img = Image.open(spritesheet_path)
    w, h = img.size
    
    # 候选帧宽
    candidates = [64, 96, 128, 192, 256]
    
    best = None
    for fw in candidates:
        if w % fw == 0:
            cols = w // fw
            # 尝试不同帧高
            for fh in candidates + [fw, fw * 2, int(fw * 1.375)]:
                if h % fh == 0:
                    rows = h // fh
                    # 优先选择合理的行列比 (8~16 列, 8~20 行)
                    if 4 <= cols <= 24 and 4 <= rows <= 24:
                        best = (fw, fh, cols, rows)
                        # 128×128 或 96×96 是最常见的
                        if fw == 128 or fw == 96:
                            return best
    
    # 如果找不到完美整除，尝试 128×128
    if w % 128 == 0 and h % 128 == 0:
        return (128, 128, w // 128, h // 128)
    
    if best:
        return best
    
    raise ValueError(
        f"无法自动检测帧尺寸 (spritesheet: {w}×{h})。\n"
        f"请手动指定: --fw <帧宽> --fh <帧高>"
    )


def convert_pet(slug: str, fw: int = None, fh: int = None):
    """将 Petdex 宠物转换为 Star-Office-UI 精灵."""
    
    # 查找 pet 目录
    pet_dir = PETDEX_DIR / slug
    if not pet_dir.exists():
        # 也检查 ~/.codex/pets/
        pet_dir = Path.home() / ".codex" / "pets" / slug
    
    if not pet_dir.exists():
        print(f"✗ 未找到宠物 '{slug}'")
        print(f"  请先运行: npx petdex install {slug}")
        sys.exit(1)
    
    # 读取 pet.json
    pet_json_path = pet_dir / "pet.json"
    if not pet_json_path.exists():
        print(f"✗ {pet_dir}/pet.json 不存在")
        sys.exit(1)
    
    with open(pet_json_path) as f:
        pet_meta = json.load(f)
    
    # 查找 spritesheet
    spritesheet = None
    for ext in [".webp", ".png"]:
        candidate = pet_dir / f"spritesheet{ext}"
        if candidate.exists():
            spritesheet = str(candidate)
            break
    
    if not spritesheet:
        print(f"✗ 未找到 spritesheet (spritesheet.webp/png)")
        sys.exit(1)
    
    print(f"📦 {pet_meta.get('displayName', slug)}")
    print(f"   来源: {spritesheet}")
    
    # 检测或使用指定的帧尺寸
    if fw and fh:
        img = Image.open(spritesheet)
        cols = img.size[0] // fw
        rows = img.size[1] // fh
        print(f"   帧尺寸: {fw}×{fh} ({cols}×{rows} = {cols*rows} 帧) [手动]")
    else:
        try:
            fw, fh, cols, rows = detect_frame_size(spritesheet)
            print(f"   帧尺寸: {fw}×{fh} ({cols}×{rows} = {cols*rows} 帧) [自动检测]")
        except ValueError as e:
            print(f"   ✗ {e}")
            sys.exit(1)
    
    # 提取第一帧作为立绘（Star-Office-UI 用单帧 sprite 显示 agent）
    img = Image.open(spritesheet)
    first_frame = img.crop((0, 0, fw, fh))
    
    # 确保输出目录存在
    STAR_OFFICE_STATIC.mkdir(parents=True, exist_ok=True)
    
    # 保存立绘
    output_name = f"petdex_{slug}"
    output_path = STAR_OFFICE_STATIC / f"{output_name}.png"
    first_frame.save(str(output_path))
    print(f"   ✓ 立绘: {output_path}")
    
    # 保存完整 spritesheet 副本
    sheet_path = STAR_OFFICE_STATIC / f"{output_name}_sheet.png"
    shutil.copy2(spritesheet, str(sheet_path))
    print(f"   ✓ 精灵表: {sheet_path}")
    
    # 保存元数据（供 game.js 加载时使用）
    meta = {
        "slug": slug,
        "displayName": pet_meta.get("displayName", slug),
        "spriteVersionNumber": pet_meta.get("spriteVersionNumber", 2),
        "frameWidth": fw,
        "frameHeight": fh,
        "columns": cols,
        "rows": rows,
        "totalFrames": cols * rows,
    }
    meta_path = STAR_OFFICE_STATIC / f"{output_name}.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"   ✓ 元数据: {meta_path}")
    
    print(f"\n✅ 转换完成!")
    print(f"   精灵 key: {output_name}")
    print(f"   使用方式:")
    print(f"     curl -X POST http://127.0.0.1:19000/set-agent-avatar \\")
    print(f"       -H 'Content-Type: application/json' \\")
    print(f"       -d '{{\"agentId\": \"<agent_id>\", \"avatar\": \"{output_name}\"}}'")
    print()
    print(f"   刷新 http://127.0.0.1:19000/ 即可看到效果")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Petdex → Star-Office-UI 精灵转换器")
    parser.add_argument("slug", help="Petdex 宠物 slug (如 boba, mallow, pikachu)")
    parser.add_argument("--fw", type=int, help="帧宽度 (如 128)")
    parser.add_argument("--fh", type=int, help="帧高度 (如 176)")
    args = parser.parse_args()
    
    convert_pet(args.slug, args.fw, args.fh)