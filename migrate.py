#!/usr/bin/env python3
"""
Hermes Portable - 数据迁移工具
将现有 Hermes 安装的数据迁移到便携式版本。
"""
import os
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
SOURCE_HOME = Path.home() / ".hermes"

# 要迁移的目录/文件
MIGRATE_ITEMS = [
    "config.yaml",
    ".env",
    "auth.json",
    "sessions",
    "skills",
    "memories",
    "cron",
    "plugins",
    "SOUL.md",
]

# 可选迁移（大文件）
OPTIONAL_ITEMS = [
    "audio_cache",
    "image_cache",
    "logs",
]

def main():
    print("=" * 50)
    print("  Hermes Portable - 数据迁移工具")
    print("=" * 50)
    print()

    if not SOURCE_HOME.exists():
        print(f"❌ 未找到现有 Hermes 安装 ({SOURCE_HOME})")
        print("   没有需要迁移的数据。")
        return

    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    migrated = []
    skipped = []

    for item in MIGRATE_ITEMS:
        src = SOURCE_HOME / item
        dst = DATA_DIR / item

        if not src.exists():
            skipped.append(item)
            continue

        if dst.exists():
            resp = input(f"⚠️  {item} 已存在，覆盖? (y/N): ").strip().lower()
            if resp != "y":
                skipped.append(item)
                continue

        print(f"📦 迁移 {item}...", end=" ")
        try:
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            print("✓")
            migrated.append(item)
        except Exception as e:
            print(f"✗ ({e})")
            skipped.append(item)

    print()
    print(f"✅ 成功迁移: {len(migrated)} 项")
    for item in migrated:
        print(f"   • {item}")

    if skipped:
        print(f"\n⏭️  跳过: {len(skipped)} 项")
        for item in skipped:
            print(f"   • {item}")

    # 大文件提示
    print()
    print("💡 可选的大文件缓存 (默认不迁移):")
    for item in OPTIONAL_ITEMS:
        src = SOURCE_HOME / item
        if src.exists():
            size = sum(f.stat().st_size for f in src.rglob("*") if f.is_file())
            size_mb = size / (1024 * 1024)
            print(f"   • {item}: {size_mb:.1f} MB")

    print()
    print("🎉 迁移完成！现在可以运行 ./start.sh 启动 Hermes Portable。")

if __name__ == "__main__":
    main()
