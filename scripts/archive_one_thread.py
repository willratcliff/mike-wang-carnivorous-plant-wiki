"""Smoke test: run the full pipeline on one thread.

Usage:
    .venv/bin/python scripts/archive_one_thread.py 5722 leucophylla-redrum-baldwin-al
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sarrwiki.pipeline import archive_thread  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("thread_id", type=int)
    ap.add_argument("slug")
    ap.add_argument("--skip-images", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore HTML cache and re-fetch")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    result = archive_thread(
        thread_id=args.thread_id,
        thread_slug=args.slug,
        raw_root=REPO_ROOT / "data" / "raw",
        parsed_root=REPO_ROOT / "data" / "parsed",
        images_root=REPO_ROOT / "data" / "images",
        skip_images=args.skip_images,
    )

    print()
    print("=" * 60)
    print(f"thread {result.thread_id} ({result.thread_slug})")
    print(f"  pages fetched: {result.pages_fetched}")
    print(f"  posts total:   {result.posts_total}")
    print(f"  images:        {result.images_ok} ok / {result.images_failed} failed / {result.images_attempted} attempted")
    if result.parser_warnings:
        print(f"  parser warnings ({len(result.parser_warnings)}):")
        for w in result.parser_warnings[:20]:
            print(f"    - {w}")
        if len(result.parser_warnings) > 20:
            print(f"    ... and {len(result.parser_warnings) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
