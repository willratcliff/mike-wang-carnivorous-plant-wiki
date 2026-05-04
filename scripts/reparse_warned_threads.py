"""Re-parse threads whose parsed JSON has parser_warnings.

Reads the cached raw HTML (no network) and re-runs the parser on each
page. Useful after fixing a parser bug.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sarrwiki.parser import parse_thread_page, write_thread_page  # noqa: E402

LOG = logging.getLogger("reparse")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="re-parse every parsed JSON, not just those with warnings")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    parsed_root = REPO_ROOT / "data" / "parsed" / "threads"
    raw_root = REPO_ROOT / "data" / "raw" / "threads"

    json_files = sorted(parsed_root.glob("*/page-*.json"))
    targets = []
    for jf in json_files:
        try:
            d = json.loads(jf.read_text())
        except json.JSONDecodeError:
            continue
        if args.all or d.get("parser_warnings"):
            raw_html = raw_root / str(d["thread_id"]) / f"page-{d['page']}.html"
            if raw_html.exists():
                targets.append((jf, raw_html, d["thread_id"], d["thread_slug"], d["page"]))

    print(f"reparsing {len(targets)} pages")
    warnings_before = 0
    warnings_after = 0
    for jf, raw_html, tid, slug, page in targets:
        old = json.loads(jf.read_text())
        warnings_before += len(old.get("parser_warnings", []))
        new = parse_thread_page(
            raw_html.read_text(encoding="utf-8", errors="replace"),
            thread_id=tid,
            thread_slug=slug,
            page=page,
            source_url=old.get("source_url"),
        )
        warnings_after += len(new.parser_warnings)
        write_thread_page(new, jf)
    print(f"parser warnings: {warnings_before} -> {warnings_after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
