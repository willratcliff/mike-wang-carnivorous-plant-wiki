"""Phase 2: walk every parsed thread JSON and mirror all images.

Reads data/parsed/threads/*/page-*.json, collects unique image_urls,
mirrors them via ImageMirror (which already deduplicates against its
manifest). Resumable — already-mirrored URLs are skipped.

Usage:
    .venv/bin/python scripts/mirror_all_images.py
    .venv/bin/python scripts/mirror_all_images.py --limit 100
    .venv/bin/python scripts/mirror_all_images.py --retry-failed
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sarrwiki.image_mirror import ImageMirror  # noqa: E402

LOG = logging.getLogger("mirror_all_images")


def collect_image_urls(parsed_threads_root: Path) -> list[str]:
    seen: dict[str, None] = {}  # ordered, dedup
    json_files = sorted(parsed_threads_root.glob("*/page-*.json"))
    for jf in json_files:
        try:
            d = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOG.warning("could not parse %s", jf)
            continue
        for post in d.get("posts", []):
            for url in post.get("image_urls", []):
                seen.setdefault(url, None)
    return list(seen.keys())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    images_root = REPO_ROOT / "data" / "images"
    parsed_threads_root = REPO_ROOT / "data" / "parsed" / "threads"

    mirror = ImageMirror(images_root=images_root)
    urls = collect_image_urls(parsed_threads_root)
    print(f"collected {len(urls)} unique image URLs from parsed threads")

    # Slice off ones already in manifest
    pending = []
    skipped_ok = 0
    skipped_failed = 0
    for u in urls:
        existing = mirror._manifest.get(u)
        if existing and existing.get("status") == "ok":
            skipped_ok += 1
            continue
        if existing and existing.get("status") == "failed" and not args.retry_failed:
            skipped_failed += 1
            continue
        pending.append(u)
    print(f"  already mirrored ok:  {skipped_ok}")
    print(f"  recorded as failed:   {skipped_failed} (use --retry-failed to retry)")
    print(f"  pending download:     {len(pending)}")

    if args.limit:
        pending = pending[:args.limit]
        print(f"  capped to:            {len(pending)} by --limit")

    if not pending:
        print("nothing to do.")
        return 0

    started = time.time()
    batch_size = 50
    total_ok = 0
    total_failed = 0
    for i in range(0, len(pending), batch_size):
        batch = pending[i:i + batch_size]
        results = mirror.mirror_urls(batch, retry_failed=args.retry_failed)
        for entry in results.values():
            if entry.status == "ok":
                total_ok += 1
            elif entry.status == "failed":
                total_failed += 1
        elapsed = time.time() - started
        done = min(i + batch_size, len(pending))
        rate = done / elapsed if elapsed > 0 else 0
        eta = (len(pending) - done) / rate if rate > 0 else 0
        print(
            f"[batch {i // batch_size + 1}] processed {done}/{len(pending)} "
            f"({total_ok} ok, {total_failed} failed) "
            f"({elapsed/60:.1f}m elapsed, eta ~{eta/60:.0f}m)"
        )

    print()
    print(f"=== mirror run complete ===")
    print(f"  total processed: {len(pending)}")
    print(f"  ok:              {total_ok}")
    print(f"  failed:          {total_failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
