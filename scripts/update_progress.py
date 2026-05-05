#!/usr/bin/env python3
"""Helper for the synthesis loop: merge a batch of new cluster entries
into data/parsed/clones/synthesis_progress.json.

Usage:
    .venv/bin/python scripts/update_progress.py /path/to/new_entries.json

The input JSON is a dict mapping cluster_id -> entry-dict (same shape
as entries already in synthesis_progress.json). Entries are merged
(replacing keys) into progress["clusters"].
"""
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("usage: update_progress.py <new_entries.json>", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(__file__).resolve().parent.parent
    progress_path = repo_root / "data/parsed/clones/synthesis_progress.json"

    with open(progress_path) as f:
        progress = json.load(f)

    with open(sys.argv[1]) as f:
        new_entries = json.load(f)

    progress["clusters"].update(new_entries)

    with open(progress_path, "w") as f:
        json.dump(progress, f, indent=2)

    print(f"Total in progress: {len(progress['clusters'])}")


if __name__ == "__main__":
    main()
