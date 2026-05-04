"""Lint the wiki/ tree.

Reports:
- Frontmatter YAML errors
- Missing required fields per entry type
- Photo paths that don't exist on disk
- source_threads referencing thread IDs not in our archive
- Orphan entries (cultivar-group with no children, child with missing parent)
- A "needs review" worklist of [VERIFY] / [MISSING] / open_questions counts

Exit code 0 if no errors; non-zero if any.

Usage:
    .venv/bin/python scripts/validate_wiki.py
    .venv/bin/python scripts/validate_wiki.py --json   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = REPO_ROOT / "wiki"
IMAGES_ROOT = REPO_ROOT / "data" / "images"
PARSED_THREADS_ROOT = REPO_ROOT / "data" / "parsed" / "threads"

REQUIRED_CLONE_FIELDS = ("full_name", "genus", "species", "review")
REQUIRED_GROUP_FIELDS = ("group_name", "genus", "species", "member_clones", "review")

VERIFY_RE = re.compile(r"\[VERIFY\]")
MISSING_RE = re.compile(r"\[MISSING\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class EntryReport:
    rel_path: Path
    type: str = "?"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verify_count: int = 0
    missing_count: int = 0
    open_question_count: int = 0
    photo_count: int = 0
    photos_missing_on_disk: int = 0
    reviewed: bool = False


def load_thread_ids() -> set[int]:
    return {int(d.name) for d in PARSED_THREADS_ROOT.iterdir() if d.is_dir() and d.name.isdigit()}


def lint_entry(path: Path, known_thread_ids: set[int]) -> EntryReport:
    rel = path.relative_to(WIKI_ROOT)
    rep = EntryReport(rel_path=rel)
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        rep.errors.append("missing or malformed frontmatter")
        return rep
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        rep.errors.append(f"YAML error: {e}")
        return rep

    body = m.group(2)
    rep.verify_count = len(VERIFY_RE.findall(text))
    rep.missing_count = len(MISSING_RE.findall(text))

    rep.type = fm.get("type", "clone")
    required = REQUIRED_GROUP_FIELDS if rep.type == "cultivar_group" else REQUIRED_CLONE_FIELDS
    for field_name in required:
        if field_name not in fm:
            rep.errors.append(f"missing required field: {field_name}")

    review = fm.get("review", {}) or {}
    if isinstance(review, dict):
        rep.reviewed = bool(review.get("human_reviewed"))
        oq = review.get("open_questions") or []
        if isinstance(oq, list):
            rep.open_question_count = len(oq)

    # Photos exist?
    photos = fm.get("photos", []) or []
    if isinstance(photos, list):
        rep.photo_count = len(photos)
        for p in photos:
            if not isinstance(p, dict):
                rep.errors.append("non-dict entry in photos[]")
                continue
            ip = p.get("path")
            if not ip:
                rep.errors.append("photos[] entry missing 'path'")
                continue
            if not (IMAGES_ROOT / ip).exists():
                rep.photos_missing_on_disk += 1

    # source_threads valid?
    for s in fm.get("source_threads", []) or []:
        if not isinstance(s, dict):
            rep.errors.append("source_threads[] entry not a dict")
            continue
        tid = s.get("thread_id")
        if tid is None:
            rep.errors.append("source_threads[] entry missing thread_id")
            continue
        if tid not in known_thread_ids:
            rep.warnings.append(f"source_thread {tid} not in our parsed archive")

    # Cultivar-group: members exist?
    if rep.type == "cultivar_group":
        members = fm.get("member_clones", []) or []
        my_dir = path.parent
        for m_slug in members:
            child_index = my_dir / str(m_slug) / "index.md"
            if not child_index.exists():
                rep.warnings.append(f"member_clones references missing dir: {m_slug}")

    # Clone: parent group exists if cultivar_group field set?
    if rep.type == "clone" and fm.get("cultivar_group"):
        parent_dir = path.parent.parent
        parent_index = parent_dir / "index.md"
        if not parent_index.exists():
            rep.warnings.append(f"cultivar_group set but no parent group at {parent_index.relative_to(WIKI_ROOT)}")

    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not WIKI_ROOT.exists():
        print(f"no wiki/ directory at {WIKI_ROOT}", file=sys.stderr)
        return 2

    known_thread_ids = load_thread_ids()
    reports = []
    for p in sorted(WIKI_ROOT.rglob("index.md")):
        reports.append(lint_entry(p, known_thread_ids))

    by_type = Counter(r.type for r in reports)
    err_count = sum(1 for r in reports if r.errors)
    warn_count = sum(1 for r in reports if r.warnings)
    reviewed = sum(1 for r in reports if r.reviewed)

    if args.json:
        out = {
            "summary": {
                "total_entries": len(reports),
                "by_type": dict(by_type),
                "with_errors": err_count,
                "with_warnings": warn_count,
                "reviewed": reviewed,
                "verify_total": sum(r.verify_count for r in reports),
                "missing_total": sum(r.missing_count for r in reports),
                "open_questions_total": sum(r.open_question_count for r in reports),
                "photos_total": sum(r.photo_count for r in reports),
                "photos_missing_on_disk_total": sum(r.photos_missing_on_disk for r in reports),
            },
            "entries": [
                {
                    "path": str(r.rel_path),
                    "type": r.type,
                    "reviewed": r.reviewed,
                    "errors": r.errors,
                    "warnings": r.warnings,
                    "verify_count": r.verify_count,
                    "missing_count": r.missing_count,
                    "open_question_count": r.open_question_count,
                    "photo_count": r.photo_count,
                    "photos_missing_on_disk": r.photos_missing_on_disk,
                }
                for r in reports
            ],
        }
        print(json.dumps(out, indent=2))
        return 1 if err_count else 0

    print(f"=== Wiki validation ===")
    print(f"  entries: {len(reports)} (clones: {by_type.get('clone', 0)}, groups: {by_type.get('cultivar_group', 0)})")
    print(f"  with errors:        {err_count}")
    print(f"  with warnings:      {warn_count}")
    print(f"  reviewed by human:  {reviewed}/{len(reports)}")
    print(f"  total [VERIFY]:     {sum(r.verify_count for r in reports)}")
    print(f"  total [MISSING]:    {sum(r.missing_count for r in reports)}")
    print(f"  total open Qs:      {sum(r.open_question_count for r in reports)}")
    print(f"  total photos:       {sum(r.photo_count for r in reports)}")
    print(f"  photos missing on disk: {sum(r.photos_missing_on_disk for r in reports)}")
    print()

    if err_count:
        print("--- ENTRIES WITH ERRORS ---")
        for r in reports:
            if r.errors:
                print(f"  {r.rel_path}")
                for e in r.errors:
                    print(f"    [error] {e}")
                for w in r.warnings:
                    print(f"    [warn ] {w}")
        print()

    if warn_count and err_count == 0:
        print("--- ENTRIES WITH WARNINGS ---")
        for r in reports:
            if r.warnings and not r.errors:
                print(f"  {r.rel_path}")
                for w in r.warnings:
                    print(f"    [warn] {w}")
        print()

    print("--- REVIEW BACKLOG (top 10 by [MISSING]+[VERIFY]+open Qs) ---")
    backlog = [(r.missing_count + r.verify_count + r.open_question_count, r) for r in reports if not r.reviewed]
    backlog.sort(reverse=True, key=lambda x: x[0])
    for score, r in backlog[:10]:
        print(f"  score={score:>3}  {r.rel_path}  ({r.verify_count} verify, {r.missing_count} missing, {r.open_question_count} open)")

    return 1 if err_count else 0


if __name__ == "__main__":
    sys.exit(main())
