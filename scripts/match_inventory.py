"""Match each plant in Mike's sales inventory to a wiki entry.

Reads the wiki lookup index (built by scripts/build_wiki_lookup.py) and
the current sales-listing CSV (Mike's site exports a snapshot from the
Google Sheet). For each row, parses the listing's name+location and
finds the best matching wiki entry.

Confidence levels:
  high    cultivar quoted in name → unique wiki entry with matching cultivar
  medium  species+variety+county+state matches a population/locality entry
  low     only species (or species+variety) matches → species index page
  none    no good match

Output: scripts/wiki-match-report.tsv (for human review by Mike).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI_LOOKUP = ROOT / "web" / "public" / "wiki-lookup.json"
DEFAULT_INVENTORY = Path("/Users/williamratcliff/Desktop/ClaudeCode/Mike website/complete_plant_data_clean.csv")
OUT = ROOT / "scripts" / "wiki-match-report.tsv"

GENUS_ABBREVS = {
    "S": "Sarracenia",
    "D": "Dionaea",
    "C": "Cephalotus",
    "U": "Utricularia",
    "Dr": "Drosera",
    "P": "Pinguicula",
}


# Sarracenia binomial species names — used to disambiguate "S. moorei"
# (where moorei is a hybrid epithet, not a true species) from "S. flava".
TRUE_SARRACENIA_SPECIES = {
    "alabamensis", "alata", "flava", "jonesii", "leucophylla", "minor",
    "oreophila", "psittacina", "purpurea", "rosea", "rubra", "montana",
}
# Other genera with one common species each on Mike's site.
TRUE_SPECIES = {
    "Sarracenia": TRUE_SARRACENIA_SPECIES,
    "Dionaea": {"muscipula"},
    "Cephalotus": {"follicularis"},
    "Drosera": {"binata", "capensis", "filiformis", "intermedia", "rotundifolia"},
}


def parse_name(name: str) -> dict:
    """Parse a sales-listing 'name' string into structured fields."""
    text = name.strip()
    is_various = "various clone" in text.lower()
    text_clean = re.sub(r"\(various clones?\)", "", text, flags=re.IGNORECASE).strip()

    # Genus: full word ("Sarracenia") OR abbreviation ("S.").
    genus = None
    genus_abbrev = None
    rest = text_clean
    m = re.match(r"^([A-Z][a-z]+)\s+", text_clean)
    if m and m.group(1) in TRUE_SPECIES:
        genus = m.group(1)
        rest = text_clean[m.end():].strip()
    else:
        m = re.match(r"^([A-Za-z]+)\.\s+", text_clean)
        if m:
            genus_abbrev = m.group(1)
            genus = GENUS_ABBREVS.get(genus_abbrev)
            rest = text_clean[m.end():].strip()

    if not genus:
        return {"genus": None, "raw": text}

    is_hybrid = False
    if re.match(r"^[x×]\s+", rest, re.IGNORECASE):
        is_hybrid = True
        rest = re.sub(r"^[x×]\s+", "", rest, flags=re.IGNORECASE).strip()

    # Look for any quoted cultivar token anywhere in the remaining text.
    cultivar = None
    cult_m = re.search(r"'([^']+)'", rest)
    if cult_m:
        cultivar = cult_m.group(1)
        rest = (rest[:cult_m.start()] + rest[cult_m.end():]).strip()

    parts = rest.split()
    species = None
    real_species = TRUE_SPECIES.get(genus, set())

    # If the next token is a true species name, take it as the species.
    # Otherwise the listing is a hybrid / genus-level cultivar — the
    # "species slot" is actually a cultivar/hybrid name (e.g. "S. Mardi
    # Gras" or "S. moorei" where moorei is a hybrid epithet, not a true
    # species). Also: a quoted cultivar with no species token at all
    # (e.g. "S. 'Waccamaw'") falls into the hybrid/genus search path.
    if parts and parts[0].lower() in real_species:
        species = parts[0].lower()
        parts = parts[1:]
    else:
        is_hybrid = True

    infra_rank = None
    infra_name = None
    if parts and parts[0].rstrip(".").lower() in ("var", "ssp", "subsp", "f"):
        infra_rank = parts[0].rstrip(".").lower()
        infra_name = parts[1].lower() if len(parts) > 1 else None
        parts = parts[2:]

    # "clone X" pattern: pick up things like "clone C" or "clone L".
    clone_letter = None
    if len(parts) >= 2 and parts[0].lower() == "clone" and len(parts[1]) <= 3:
        clone_letter = parts[1].rstrip(",").upper()
        parts = parts[2:]

    # Anything left over: if hybrid OR no cultivar yet, treat as the
    # cultivar text (covers "S. moorei red throat", "S. x Mardi Gras",
    # "S. moorei Wilkerson's White Knight").
    leftover = " ".join(parts).strip()
    if leftover and not cultivar:
        cultivar = leftover

    return {
        "genus": genus,
        "genus_abbrev": genus_abbrev,
        "species": species,
        "is_hybrid": is_hybrid,
        "infraspecific_rank": infra_rank,
        "infraspecific_name": infra_name,
        "cultivar": cultivar,
        "clone_letter": clone_letter,
        "is_various": is_various,
        "raw": text,
    }


# Regex captures "<county>, <state>" patterns with abbreviations like
# "Liberty Co, FL" or "Bulloch County, GA". State is two-letter
# uppercase US-state abbreviation.
LOCATION_RE = re.compile(
    r"([A-Za-z\.\s]+?)\s*(?:Co\.?|County)\s*,?\s*([A-Z]{2})\b",
    re.IGNORECASE,
)


def parse_location(loc: str) -> tuple[str | None, str | None]:
    if not loc:
        return None, None
    m = LOCATION_RE.search(loc)
    if m:
        county = m.group(1).strip()
        state = m.group(2).upper()
        return state, county
    # "Brunswick Co, NC" worked above. Fallback: bare state at end.
    state_only = re.search(r",\s*([A-Z]{2})\s*$", loc)
    if state_only:
        return state_only.group(1).upper(), None
    return None, None


def norm(s: str | None) -> str:
    return (s or "").lower().strip()


def find_match(parsed: dict, location: str, wiki: list[dict]) -> tuple[dict | None, str, list[dict]]:
    """Return (best_match, confidence, candidates)."""
    if not parsed.get("genus"):
        return None, "none", []
    genus = norm(parsed["genus"])

    state, county = parse_location(location)

    # No-species path: typical for hybrids ("S. x Mardi Gras") and for
    # cultivars whose listing omits the species ("S. 'Waccamaw'"). Search
    # the whole genus by cultivar, preferring the hybrid pool first then
    # falling back to species-level entries.
    if parsed.get("is_hybrid") and parsed.get("cultivar"):
        cult = norm(parsed["cultivar"])
        in_genus = [w for w in wiki if norm(w["genus"]) == genus]
        hybrids = [w for w in in_genus if w.get("hybrid")]
        for pool, conf in [(hybrids, "high"), (in_genus, "high")]:
            cult_hits = [w for w in pool if norm(w.get("cultivar")) == cult]
            if cult_hits:
                return cult_hits[0], conf, cult_hits[:5]
            short_hits = [w for w in pool if cult == norm(w.get("short_name"))]
            if short_hits:
                return short_hits[0], conf, short_hits[:5]
        for pool in (hybrids, in_genus):
            sub_hits = [
                w for w in pool
                if cult and (cult in norm(w.get("full_name")) or cult in norm(w.get("short_name")))
            ]
            if sub_hits:
                return sub_hits[0], "medium", sub_hits[:5]
        return None, "none", []

    if not parsed.get("species"):
        return None, "none", []
    species = norm(parsed["species"])

    base = [
        w for w in wiki
        if norm(w["genus"]) == genus and norm(w["species"]) == species
    ]
    if not base:
        return None, "none", []

    var_l = norm(parsed.get("infraspecific_name"))

    # Tier 1 (high): cultivar match within the same variety.
    if parsed.get("cultivar") and not parsed.get("is_various"):
        cult = norm(parsed["cultivar"])
        # Filter to the listing's variety (or null variety on both sides).
        same_var = [
            w for w in base
            if norm(w.get("infraspecific_name")) == var_l
        ] if var_l else base
        # Prefer exact cultivar field match.
        exact = [w for w in same_var if norm(w.get("cultivar")) == cult]
        if exact:
            return exact[0], "high", exact[:5]
        # Fallback: cultivar substring in full_name / short_name, but
        # only within the same variety so we don't leak across varieties.
        sub = [
            w for w in same_var
            if cult in norm(w.get("full_name")) or cult in norm(w.get("short_name"))
        ]
        if sub:
            return sub[0], "high", sub[:5]

    # "clone X" letter match — try cultivar=="clone X" or slug matching.
    if parsed.get("clone_letter") and var_l:
        letter = parsed["clone_letter"].lower()
        same_var = [w for w in base if norm(w.get("infraspecific_name")) == var_l]
        if state and county:
            same_var = [
                w for w in same_var
                if norm(w.get("state")) == norm(state) and norm(w.get("county")) == norm(county)
            ] or same_var
        slug_hits = [w for w in same_var if f"/clone-{letter}-" in w["id"] or w["id"].endswith(f"/clone-{letter}")]
        if slug_hits:
            return slug_hits[0], "high", slug_hits[:5]

    # Tier 2 (medium): species + variety + county + state.
    if var_l and county and state:
        loc_matches = [
            w for w in base
            if norm(w.get("infraspecific_name")) == var_l
            and norm(w.get("state")) == norm(state)
            and norm(w.get("county")) == norm(county)
        ]
        if loc_matches:
            return loc_matches[0], "medium", loc_matches[:5]

    # Tier 3 (low): species + variety match.
    if var_l:
        var_matches = [w for w in base if norm(w.get("infraspecific_name")) == var_l]
        if var_matches:
            return var_matches[0], "low", var_matches[:5]

    # Tier 4 (low): just species.
    return base[0], "low", base[:5]


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)

    if not WIKI_LOOKUP.exists():
        print(f"missing {WIKI_LOOKUP} — run scripts/build_wiki_lookup.py first", file=sys.stderr)
        return 1
    if not args.inventory.exists():
        print(f"inventory not found: {args.inventory}", file=sys.stderr)
        return 1

    wiki = json.loads(WIKI_LOOKUP.read_text())
    rows = list(csv.DictReader(args.inventory.open()))

    out_rows: list[dict] = []
    counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for r in rows:
        parsed = parse_name(r.get("name", ""))
        match, conf, cands = find_match(parsed, r.get("location", ""), wiki)
        counts[conf] += 1
        out_rows.append({
            "plant_id": r.get("id", ""),
            "plant_name": r.get("name", ""),
            "plant_location": r.get("location", ""),
            "parsed_genus": parsed.get("genus") or "",
            "parsed_species": parsed.get("species") or "",
            "parsed_var": parsed.get("infraspecific_name") or "",
            "parsed_cultivar": parsed.get("cultivar") or "",
            "is_various": "yes" if parsed.get("is_various") else "",
            "match_path": match["id"] if match else "",
            "confidence": conf,
            "match_full_name": match.get("full_name") if match else "",
            "candidate_count": str(len(cands)),
            "alt_paths": " | ".join(c["id"] for c in cands[1:5]),
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        w = csv.DictWriter(f, fieldnames=out_rows[0].keys(), delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)

    # Starter overrides file: every HIGH match (most confident, least
    # review burden). Mike copies this into his repo as
    # `wiki-overrides.json`, deletes any wrong matches, adds entries
    # for missed clones, and sets a value to false to suppress a link.
    starter_path = args.out.parent / "wiki-overrides.starter.json"
    starter = {
        r["plant_id"]: r["match_path"]
        for r in out_rows
        if r["confidence"] == "high" and r["match_path"]
    }
    starter_path.write_text(json.dumps(starter, indent=2, sort_keys=True))

    total = len(out_rows)
    print(f"matched {total} listings:")
    for k in ("high", "medium", "low", "none"):
        n = counts[k]
        pct = 100 * n / max(total, 1)
        print(f"  {k:8s}: {n:4d}  ({pct:.0f}%)")
    print(f"\nreport: {args.out}")
    print(f"starter overrides: {starter_path}  ({len(starter)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
