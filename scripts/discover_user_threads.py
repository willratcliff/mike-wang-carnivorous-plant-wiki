"""Walk /user/<id>/recent_threads pagination to enumerate all threads
started by a user.

Output: data/parsed/users/<id>/threads.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import datetime as dt
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sarrwiki.fetcher import Fetcher  # noqa: E402
from sarrwiki.parser import parse_user_recent_threads  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id", type=int, help="numeric forum user id (e.g. 11 for meizzwang)")
    ap.add_argument("--max-pages", type=int, default=None, help="stop after N pages (default: all)")
    ap.add_argument("--force", action="store_true", help="ignore cached HTML")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    raw_root = REPO_ROOT / "data" / "raw"
    parsed_root = REPO_ROOT / "data" / "parsed" / "users" / str(args.user_id)
    parsed_root.mkdir(parents=True, exist_ok=True)

    fetcher = Fetcher(raw_root=raw_root)

    # Page 1 first to learn total_pages
    fr = fetcher.fetch_user_recent_threads(args.user_id, page=1, force=args.force)
    if fr.status_code != 200 and not fr.from_cache:
        print(f"FAIL page 1: HTTP {fr.status_code}", file=sys.stderr)
        return 1

    page1 = parse_user_recent_threads(
        fr.path.read_text(encoding="utf-8"),
        user_id=args.user_id,
        page=1,
        source_url=fr.url,
    )
    total_pages = page1["total_pages"]
    print(f"discovered {total_pages} total pages of threads for user {args.user_id}")
    if args.max_pages:
        total_pages = min(total_pages, args.max_pages)
        print(f"capped to {total_pages} pages by --max-pages")

    all_threads_by_id: dict[int, dict] = {}
    for t in page1["threads"]:
        all_threads_by_id[t["thread_id"]] = t

    for page in range(2, total_pages + 1):
        fr = fetcher.fetch_user_recent_threads(args.user_id, page=page, force=args.force)
        if fr.status_code != 200 and not fr.from_cache:
            print(f"WARN page {page}: HTTP {fr.status_code} — continuing", file=sys.stderr)
            continue
        parsed = parse_user_recent_threads(
            fr.path.read_text(encoding="utf-8"),
            user_id=args.user_id,
            page=page,
            source_url=fr.url,
        )
        for t in parsed["threads"]:
            all_threads_by_id[t["thread_id"]] = t

    out = {
        "user_id": args.user_id,
        "total_pages_seen": total_pages,
        "thread_count": len(all_threads_by_id),
        "threads": sorted(all_threads_by_id.values(), key=lambda x: x["thread_id"]),
        "discovered_at_iso": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    out_path = parsed_root / "threads.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path} ({len(all_threads_by_id)} unique threads)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
