"""Generate per-thread Markdown bundles for every parsed thread.

Reads:  data/parsed/threads/*/page-*.json
        data/images/manifest.json
Writes: data/bundles/threads/<id>.md  (one per thread)
        data/bundles/threads/index.md  (catalog)
"""

from __future__ import annotations

import argparse
import json
import sys
import datetime as dt
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sarrwiki.bundle import (  # noqa: E402
    collect_thread_pages,
    load_image_manifest,
    write_bundle,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--thread-id", type=int, default=None,
                    help="render only one specific thread, then stop")
    ap.add_argument("--image-prefix", default="../../images/",
                    help="path prefix to local mirrored images, relative to bundle file")
    args = ap.parse_args()

    parsed_root = REPO_ROOT / "data" / "parsed" / "threads"
    manifest_path = REPO_ROOT / "data" / "images" / "manifest.json"
    out_root = REPO_ROOT / "data" / "bundles"
    out_root.mkdir(parents=True, exist_ok=True)

    manifest = load_image_manifest(manifest_path)
    print(f"loaded manifest with {len(manifest)} entries")

    thread_ids: list[int] = []
    if args.thread_id is not None:
        thread_ids = [args.thread_id]
    else:
        for tdir in parsed_root.iterdir():
            if tdir.is_dir() and tdir.name.isdigit():
                thread_ids.append(int(tdir.name))
        thread_ids.sort()
    if args.limit:
        thread_ids = thread_ids[:args.limit]

    print(f"rendering {len(thread_ids)} threads")

    written = []
    skipped = []
    for tid in thread_ids:
        out = write_bundle(
            thread_id=tid,
            parsed_threads_root=parsed_root,
            manifest=manifest,
            out_root=out_root,
            image_path_prefix=args.image_prefix,
        )
        if out is None:
            skipped.append(tid)
            continue
        written.append((tid, out))

    if args.thread_id is None:
        # Build a simple catalog index
        index_lines = [
            "# Thread bundle index",
            "",
            f"_Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}._",
            "",
            f"{len(written)} bundles below. Each links to the per-thread Markdown rendering.",
            "",
            "| Thread ID | Title | Board | Posts |",
            "| ---: | --- | --- | ---: |",
        ]
        index_path = out_root / "threads" / "index.md"
        for tid, out in written:
            pages = collect_thread_pages(parsed_root, tid)
            title = pages[0].get("thread_title") if pages else f"thread {tid}"
            board = pages[0].get("board_title") if pages else ""
            posts = sum(len(p.get("posts", [])) for p in pages)
            # Link relative to the index file's directory
            rel = out.relative_to(index_path.parent)
            safe_title = (title or "").replace("|", "\\|")
            index_lines.append(f"| {tid} | [{safe_title}]({rel}) | {board or ''} | {posts} |")
        index_path.write_text("\n".join(index_lines), encoding="utf-8")
        print(f"wrote index: {index_path}")

    print(f"\ndone. wrote {len(written)} bundles, skipped {len(skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
