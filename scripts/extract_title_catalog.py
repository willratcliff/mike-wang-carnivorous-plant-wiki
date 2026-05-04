"""Run the heuristic title parser over all of Mike's discovered threads
and write a draft catalog to data/parsed/users/11/title_catalog.json.

The output is INTENDED FOR REVIEW. Mike should look through it and
correct misclassifications.
"""

from __future__ import annotations

import argparse
import json
import sys
import datetime as dt
from collections import Counter
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sarrwiki.title_parse import parse_title  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id", type=int, default=11, nargs="?")
    args = ap.parse_args()

    discovery_path = REPO_ROOT / "data" / "parsed" / "users" / str(args.user_id) / "threads.json"
    out_path = REPO_ROOT / "data" / "parsed" / "users" / str(args.user_id) / "title_catalog.json"
    discovered = json.loads(discovery_path.read_text())

    entries = []
    for t in discovered["threads"]:
        ext = parse_title(t["title"])
        entries.append({
            "thread_id": t["thread_id"],
            "thread_slug": t["thread_slug"],
            **asdict(ext),
        })

    out = {
        "user_id": args.user_id,
        "generated_at_iso": dt.datetime.now(dt.timezone.utc).isoformat(),
        "schema_version": 1,
        "warning": "Heuristic title-parsed catalog. Verify every entry before use.",
        "entries": entries,
    }
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {out_path}")

    cls_counts = Counter(e["classified"] for e in entries)
    print(f"\nclassification:")
    for k, n in cls_counts.most_common():
        print(f"  {k}: {n}")

    clone_entries = [e for e in entries if e["classified"] == "clone-candidate"]
    genus_counts = Counter(e["genus"] for e in clone_entries)
    print(f"\ngenus distribution (clone-candidate only):")
    for k, n in genus_counts.most_common():
        print(f"  {k}: {n}")

    species_counts = Counter(e["species"] for e in clone_entries if e["genus"] == "Sarracenia")
    print(f"\nSarracenia species distribution:")
    for k, n in species_counts.most_common(15):
        print(f"  {k}: {n}")

    state_counts = Counter(e["state"] for e in clone_entries if e["state"])
    print(f"\ntop states:")
    for k, n in state_counts.most_common(15):
        print(f"  {k}: {n}")

    cultivar_count = sum(1 for e in clone_entries if e["cultivar"])
    location_count = sum(1 for e in clone_entries if e["county"] and e["state"])
    print(f"\nentries with cultivar name: {cultivar_count}/{len(clone_entries)}")
    print(f"entries with county+state:   {location_count}/{len(clone_entries)}")

    note_counts = Counter()
    for e in clone_entries:
        for n in e.get("notes", []):
            note_counts[n] += 1
    if note_counts:
        print(f"\nparser notes (clone-candidates):")
        for n, c in note_counts.most_common():
            print(f"  [{c}] {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
