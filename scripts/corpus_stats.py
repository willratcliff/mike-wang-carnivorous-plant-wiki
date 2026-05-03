"""Summarize the parsed-thread corpus.

Designed to inform the next phase (clone synthesis): which boards have
the most Mike-authored threads, how concentrated post authorship is,
how many images we're dealing with, etc.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mike-only", action="store_true",
                    help="restrict post-level stats to posts authored by meizzwang (user 11)")
    args = ap.parse_args()

    parsed_threads = REPO_ROOT / "data" / "parsed" / "threads"
    files = sorted(parsed_threads.glob("*/page-*.json"))
    if not files:
        print(f"no parsed thread JSON found under {parsed_threads}", file=sys.stderr)
        return 1

    threads_by_id: dict[int, dict] = {}
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        tid = d["thread_id"]
        if tid not in threads_by_id:
            threads_by_id[tid] = {
                "thread_id": tid,
                "thread_title": d.get("thread_title"),
                "board_id": d.get("board_id"),
                "board_title": d.get("board_title"),
                "total_pages": d.get("total_pages", 1),
                "posts": [],
            }
        threads_by_id[tid]["posts"].extend(d.get("posts", []))

    print(f"parsed pages:   {len(files)}")
    print(f"unique threads: {len(threads_by_id)}")

    # Boards
    boards = Counter()
    for t in threads_by_id.values():
        boards[(t["board_id"], t["board_title"])] += 1
    print()
    print("Threads per board:")
    for (bid, btitle), n in boards.most_common():
        print(f"  {n:>4}  [{bid}] {btitle}")

    # Post counts per thread (and Mike-only)
    post_counts = []
    mike_post_counts = []
    image_counts_total = []
    image_counts_mike = []
    earliest = None
    latest = None
    no_mike_threads = []

    for t in threads_by_id.values():
        all_posts = t["posts"]
        mike_posts = [p for p in all_posts if p.get("author_user_id") == 11]
        post_counts.append(len(all_posts))
        mike_post_counts.append(len(mike_posts))

        n_imgs_total = sum(len(p.get("image_urls", [])) for p in all_posts)
        n_imgs_mike = sum(len(p.get("image_urls", [])) for p in mike_posts)
        image_counts_total.append(n_imgs_total)
        image_counts_mike.append(n_imgs_mike)

        if not mike_posts:
            no_mike_threads.append((t["thread_id"], t.get("thread_title")))

        for p in all_posts:
            ts = p.get("timestamp_iso")
            if ts:
                if earliest is None or ts < earliest:
                    earliest = ts
                if latest is None or ts > latest:
                    latest = ts

    def stats(values: list[int]) -> str:
        if not values:
            return "(empty)"
        s = sorted(values)
        n = len(s)
        return (
            f"n={n} min={s[0]} p25={s[n // 4]} median={s[n // 2]} "
            f"p75={s[3 * n // 4]} max={s[-1]} sum={sum(values)}"
        )

    print()
    print("Posts per thread (all authors): " + stats(post_counts))
    print("Mike-authored posts per thread: " + stats(mike_post_counts))
    print()
    print("Images per thread (all authors): " + stats(image_counts_total))
    print("Images per thread (Mike only):   " + stats(image_counts_mike))
    print()
    print(f"Earliest post timestamp: {earliest}")
    print(f"Latest post timestamp:   {latest}")

    if no_mike_threads:
        print()
        print(f"Threads with NO Mike-authored posts ({len(no_mike_threads)}):")
        for tid, title in no_mike_threads[:20]:
            print(f"  [{tid}] {title}")
        if len(no_mike_threads) > 20:
            print(f"  ... and {len(no_mike_threads) - 20} more")

    # Image hosts
    hosts = Counter()
    for t in threads_by_id.values():
        posts = t["posts"]
        if args.mike_only:
            posts = [p for p in posts if p.get("author_user_id") == 11]
        for p in posts:
            for u in p.get("image_urls", []):
                h = urlparse(u).hostname or "?"
                hosts[h] += 1
    print()
    print(f"Top image hosts ({'mike-only' if args.mike_only else 'all authors'}):")
    for h, n in hosts.most_common(15):
        print(f"  {n:>5}  {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
