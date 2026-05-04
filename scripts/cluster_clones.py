"""Cluster threads that describe the same clone.

Strategy:

1. Read the title-parsed catalog (data/parsed/users/11/title_catalog.json).
2. For each clone-candidate thread, derive a "clone key" from the most
   discriminating fields available. Preference order:

   a) (genus, species, infraspecific, cultivar, county, state)  — ideal
   b) (genus, species, infraspecific, cultivar)                  — when no location
   c) (genus, species, infraspecific, county, state)             — wild clone, no cultivar
   d) (thread_id)                                                — fallback: not clusterable yet

3. Group threads by clone key. Output one cluster per key.

The output is a draft. The synthesis layer will treat each cluster as
ONE clone (per the user's "synthesize across threads" decision). Mike
can review and split/merge as needed.

Output: data/parsed/clones/clusters.json
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def normalize(s):
    if s is None:
        return None
    s = str(s).strip().lower()
    return s or None


# Cultivar names that are too generic to be reliable cluster keys (these
# often describe a trait, not a unique clone — e.g., 4 different "red"
# clones from different sites). When the cultivar value is one of these,
# we require additional discriminators (location) to merge.
GENERIC_CULTIVAR_TOKENS = {
    "red", "dark", "giant", "white", "pink", "yellow", "purple",
    "best clone", "best of batch", "small", "large", "tall",
    "rare", "wild", "nice",
}


def derive_clone_key(entry: dict) -> tuple[str, tuple]:
    """Return (level, key) where level is which preference rule produced
    the key.

    Merge policy:
    - Levels a, a-noplant, b, b-nospecies merge by cultivar name (strong
      signal that this is a named clone shared across threads).
    - Level c (location only, no cultivar) does NOT merge — different
      clones from the same wild site should not be conflated. Each
      thread becomes its own cluster.
    - Generic cultivar tokens (e.g. "red") only merge when location also
      matches (a/a-noplant level), never at level b alone.
    """
    genus = normalize(entry.get("genus"))
    species = normalize(entry.get("species"))
    infra_rank = normalize(entry.get("infraspecific_rank"))
    infra_name = normalize(entry.get("infraspecific_name"))
    cultivar = normalize(entry.get("cultivar"))
    county = normalize(entry.get("county"))
    state = normalize(entry.get("state"))

    has_loc = bool(county and state)
    has_cult = bool(cultivar)
    cult_is_generic = has_cult and cultivar in GENERIC_CULTIVAR_TOKENS

    if genus and species and has_cult and has_loc:
        return ("a", (genus, species, infra_rank, infra_name, cultivar, county, state))
    if genus and has_cult and has_loc:
        return ("a-noplant", (genus, None, infra_rank, infra_name, cultivar, county, state))
    if genus and species and has_cult and not cult_is_generic:
        return ("b", (genus, species, infra_rank, infra_name, cultivar))
    if genus and has_cult and not cult_is_generic:
        return ("b-nospecies", (genus, None, infra_rank, infra_name, cultivar))
    # No safe merge. Each thread = its own cluster.
    return ("c-singleton", ("thread", entry.get("thread_id")))


def main() -> int:
    catalog_path = REPO_ROOT / "data" / "parsed" / "users" / "11" / "title_catalog.json"
    catalog = json.loads(catalog_path.read_text())

    # Bucket: key -> list of entries
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    levels: dict[tuple, str] = {}
    others: list[dict] = []

    for entry in catalog["entries"]:
        if entry.get("classified") != "clone-candidate":
            others.append({
                "thread_id": entry["thread_id"],
                "title": entry.get("original_title"),
                "reason": "title classified as 'other'",
            })
            continue
        level, key = derive_clone_key(entry)
        buckets[key].append(entry)
        levels[key] = level

    clusters = []
    cluster_id = 0
    for key, members in buckets.items():
        cluster_id += 1
        sample = members[0]

        # Candidate name: build from the most-specific available fields
        parts = []
        if sample.get("genus"): parts.append(sample["genus"])
        if sample.get("species"): parts.append(sample["species"])
        if sample.get("infraspecific_rank") and sample.get("infraspecific_name"):
            parts.append(sample["infraspecific_rank"])
            parts.append(sample["infraspecific_name"])
        if sample.get("cultivar"): parts.append(f"'{sample['cultivar']}'")
        loc = ""
        if sample.get("county") and sample.get("state"):
            loc = f"{sample['county']} Co, {sample['state']}"
        candidate_name = " ".join(parts)
        if loc:
            candidate_name = f"{candidate_name} {loc}".strip()

        clusters.append({
            "cluster_id": f"C{cluster_id:04d}",
            "level": levels[key],
            "candidate_name": candidate_name,
            "candidate_genus": sample.get("genus"),
            "candidate_species": sample.get("species"),
            "candidate_infraspecific_rank": sample.get("infraspecific_rank"),
            "candidate_infraspecific_name": sample.get("infraspecific_name"),
            "candidate_cultivar": sample.get("cultivar"),
            "candidate_county": sample.get("county"),
            "candidate_state": sample.get("state"),
            "source_thread_ids": sorted(m["thread_id"] for m in members),
            "source_titles": [m.get("original_title") for m in members],
            "thread_count": len(members),
        })

    # Sort: bigger clusters first (they reveal where the synthesis work lies)
    clusters.sort(key=lambda c: (-c["thread_count"], c["candidate_name"]))

    out = {
        "generated_at_iso": dt.datetime.now(dt.timezone.utc).isoformat(),
        "schema_version": 1,
        "summary": {
            "total_clusters": len(clusters),
            "clusters_by_level": {
                lvl: sum(1 for c in clusters if c["level"] == lvl)
                for lvl in sorted({c["level"] for c in clusters})
            },
            "multi_thread_clusters": sum(1 for c in clusters if c["thread_count"] > 1),
            "singleton_clusters": sum(1 for c in clusters if c["thread_count"] == 1),
            "non_clone_threads": len(others),
        },
        "clusters": clusters,
        "non_clone_threads": others,
    }

    out_dir = REPO_ROOT / "data" / "parsed" / "clones"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "clusters.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {out_path}")

    print("\nSummary:")
    for k, v in out["summary"].items():
        print(f"  {k}: {v}")

    print("\nMulti-thread clusters (top 15 by size):")
    for c in clusters[:15]:
        if c["thread_count"] > 1:
            print(f"  [{c['cluster_id']}] {c['thread_count']:>2} threads — {c['candidate_name']!r}")
        else:
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
