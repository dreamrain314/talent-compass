"""清理 data/intermediate/ 中的测试残留 JSON 文件

保留带有正常 trace_id 的中间文件（如 TC-20260721-*），
只清理测试产生且不再需要的文件（pipe-test、timeout-test、test-fallback、debug-pipe 等模式）。

用法：
    python scripts/clean_intermediate.py          # 预览（列出但不删除）
    python scripts/clean_intermediate.py --run    # 实际删除
"""
import argparse
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTERMEDIATE_DIR = PROJECT_ROOT / "data" / "intermediate"

# 测试残留文件名称模式（匹配文件名包含这些关键词的 .json 文件）
TEST_PATTERNS = [
    "pipe-test",
    "timeout-test",
    "test-fallback",
    "debug-pipe",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="清理 data/intermediate/ 中的测试残留文件")
    parser.add_argument("--run", action="store_true", help="实际删除文件（默认仅预览）")
    args = parser.parse_args()

    if not INTERMEDIATE_DIR.exists():
        print(f"目录不存在: {INTERMEDIATE_DIR}")
        return

    candidates = [
        f for f in INTERMEDIATE_DIR.iterdir()
        if f.is_file() and f.suffix == ".json"
        and any(pattern in f.name for pattern in TEST_PATTERNS)
    ]

    if not candidates:
        print(f"未找到匹配测试模式的残留文件（{INTERMEDIATE_DIR}）")
        return

    print(f"找到 {len(candidates)} 个测试残留文件:")
    for f in sorted(candidates):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name}  ({size_kb:.1f} KB)")

    if args.run:
        count = 0
        for f in candidates:
            try:
                f.unlink()
                count += 1
            except OSError as e:
                print(f"  [失败] {f.name}: {e}")
        print(f"\n已删除 {count}/{len(candidates)} 个文件")
    else:
        print(f"\n预览模式：共 {len(candidates)} 个文件，使用 --run 参数实际删除")


if __name__ == "__main__":
    main()
