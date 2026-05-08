"""Generate web/public/wiki-lookup.json — a small searchable index of
every wiki entry, designed for cross-site consumption (e.g. Mike's
sales site at mikesplants.com fetches this and joins each plant
listing to a wiki URL).

Each entry:
  {
    id:                "sarracenia/flava/var-rubricorpora/bay-co-fl-population",
    genus:             "sarracenia",
    species:           "flava",
    infraspecific_rank:"var",
    infraspecific_name:"rubricorpora",
    cultivar:          null,
    full_name:         "Sarracenia flava var. rubricorpora Bay Co, FL",
    short_name:        "rubricorpora Bay Co",
    state:             "FL",
    county:            "Bay",
    photo_count:       69,
    has_favorite:      true
  }

The file is published at /wiki-lookup.json on the deployed site.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "wiki-lookup.json"


def parse_frontmatter(text: str) -> dict | None:
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    return yaml.safe_load(m.group(1))


def main() -> None:
    files = sorted(glob.glob(str(ROOT / "wiki" / "**" / "index.md"), recursive=True))
    out: list[dict] = []
    for f in files:
        text = Path(f).read_text()
        fm = parse_frontmatter(text)
        if not fm:
            continue

        # Slug = path under wiki/ minus /index.md.
        rel = Path(f).relative_to(ROOT / "wiki")
        slug = str(rel.parent).replace("\\", "/")

        loc = fm.get("origin_locality") or {}
        photos = fm.get("photos") or []

        # Treat any entry under wiki/<genus>/hybrids/ as hybrid even if
        # the frontmatter doesn't carry hybrid: true (some hybrid epithets
        # like 'moorei' are stored with a species field).
        is_hybrid = bool(fm.get("hybrid")) or "/hybrids/" in slug

        out.append({
            "id": slug,
            "genus": (fm.get("genus") or "").lower(),
            "species": fm.get("species"),
            "infraspecific_rank": fm.get("infraspecific_rank"),
            "infraspecific_name": fm.get("infraspecific_name"),
            "cultivar": fm.get("cultivar"),
            "hybrid": is_hybrid,
            "full_name": fm.get("full_name") or fm.get("group_name"),
            "short_name": fm.get("short_name"),
            "state": loc.get("state"),
            "county": loc.get("county"),
            "photo_count": len(photos),
            "has_favorite": any(p.get("favorite") for p in photos),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} entries, "
          f"{OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
