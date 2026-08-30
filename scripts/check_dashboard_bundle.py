"""Enforce a simple size budget for the generated static dashboard."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-total-mb", type=float, default=150.0)
    parser.add_argument("--max-file-mb", type=float, default=60.0)
    args = parser.parse_args()

    files = [path for path in args.path.rglob("*") if path.is_file()]
    if not files:
        raise SystemExit(f"dashboard bundle is empty: {args.path}")
    total = sum(path.stat().st_size for path in files)
    largest = max(files, key=lambda path: path.stat().st_size)
    total_mb = total / 1024 / 1024
    largest_mb = largest.stat().st_size / 1024 / 1024
    if total_mb > args.max_total_mb or largest_mb > args.max_file_mb:
        raise SystemExit(
            f"dashboard bundle exceeds budget: total={total_mb:.1f} MB, "
            f"largest={largest_mb:.1f} MB ({largest})"
        )
    print(
        f"PASS dashboard bundle: {len(files)} files, {total_mb:.1f} MB total, "
        f"{largest_mb:.1f} MB largest"
    )


if __name__ == "__main__":
    main()
