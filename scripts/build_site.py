"""Build the static site from wiki/ into _site/.

Usage:
    .venv/bin/python scripts/build_site.py
    .venv/bin/python scripts/build_site.py --no-images   # skip copying images (faster iteration)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sarrwiki.site import build_site  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-images", action="store_true",
                    help="don't copy images into _site/ (faster for layout iteration)")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    summary = build_site(
        wiki_root=REPO_ROOT / "wiki",
        images_root=REPO_ROOT / "data" / "images",
        site_root=REPO_ROOT / args.out,
        copy_images=not args.no_images,
    )
    print(f"\nbuilt {summary.pages_written} pages")
    print(f"linked {summary.images_linked} images")
    if summary.skipped:
        print(f"skipped {len(summary.skipped)} entries (see log)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
