"""Heuristic parser for Mike Wang's thread titles.

The output is **draft** — Mike must verify every entry. The parser
preserves the original title verbatim so a reviewer can always see what
was input. It surfaces:

- inferred genus + species (string-matched against a hand-written list
  of genera and the common Sarracenia species)
- inferred infraspecific rank/name (var. / ssp. / f.)
- inferred cultivar name (text in single quotes)
- inferred location: county and state (US two-letter postal codes,
  Canadian province codes, or named regions)
- a parenthetical "extras" string (parentage, breeder, etc.)

If the title doesn't match the clone-description pattern at all (e.g.,
discussion threads), the parser returns ``classified="other"`` with the
original title preserved.

Heuristics — DO NOT TRUST WITHOUT REVIEW.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ----------------------------------------------------------------------
# Vocabulary
# ----------------------------------------------------------------------

# Genera Mike works with, in canonical capitalized form, plus their
# common abbreviations. Order matters — longer forms first so we don't
# match "S." before "Sarracenia".
# Note: genus regexes use a leading word boundary plus optional period
# rather than `\bGenus\.\b` because `\b` does not match between two
# non-word characters (e.g., `.` followed by ` `).
GENUS_PATTERNS = [
    ("Sarracenia", re.compile(r"(?:^|[^a-z])(?:Sarracenia|S\.)(?=\s|$)", re.IGNORECASE)),
    ("Darlingtonia", re.compile(r"\bDarlingtonia\b", re.IGNORECASE)),
    ("Cephalotus", re.compile(r"\bCephalotus\b", re.IGNORECASE)),
    ("Drosera", re.compile(r"\b(?:Drosera)\b|(?:^|[^a-z])D\.(?=\s|$)", re.IGNORECASE)),
    ("Dionaea", re.compile(r"\b(?:Dionaea|VFT|venus\s*fly\s*trap)\b", re.IGNORECASE)),
    ("Nepenthes", re.compile(r"\b(?:Nepenthes)\b|(?:^|[^a-z])N\.(?=\s|$)", re.IGNORECASE)),
    ("Heliamphora", re.compile(r"\bHeliamphora\b", re.IGNORECASE)),
    ("Pinguicula", re.compile(r"\b(?:Pinguicula|Ping)\b", re.IGNORECASE)),
    ("Utricularia", re.compile(r"\bUtricularia\b", re.IGNORECASE)),
    ("Sabatia", re.compile(r"\bSabatia\b", re.IGNORECASE)),
    ("Platanthera", re.compile(r"\bPlatanthera\b", re.IGNORECASE)),
    ("Delphinium", re.compile(r"\bDelphinium\b", re.IGNORECASE)),
]

# Sarracenia species names (lowercase). When we see these as a bare
# word after "S." or "Sarracenia", they're the species.
SARRACENIA_SPECIES = {
    "alata", "flava", "leucophylla", "minor", "oreophila", "psittacina",
    "purpurea", "rubra", "rosea", "moorei", "charlesmoorei",
    "okefenokeensis",  # treated as species sometimes, var sometimes
    "alabamensis", "alabamenesis",  # alabamensis + common typo
    "jonesii",
    "montana",
    "catesbaei", "excellens", "umlauftiana", "tapestry",  # known hybrid epithets
    # Common abbreviations
    "purp", "leuco", "psitt", "rub", "oreo",
}

# Common infraspecific markers
INFRA_RE = re.compile(
    r"\b(?P<rank>var\.|ssp\.|subsp\.|f\.|forma|x|×)\s*(?P<name>[a-zA-Z0-9-]+)",
    re.IGNORECASE,
)

# Cultivar name: text in single quotes (curly or straight)
CULTIVAR_RE = re.compile(r"['‘’]([^'‘’]{1,80})['‘’]")

# US states + Canadian provinces (2-letter codes used in titles)
STATE_CODES = {
    # US
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    # Canadian provinces
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT",
}

# Location pattern: "<County> Co, <STATE>" or "<County> Co <STATE>"
# The county can be multi-word (e.g., "St. Tammany Parish")
COUNTY_RE = re.compile(
    r"(?P<county>(?:[A-Z][\w\.]*\s*){1,5})\s+"
    r"(?:Co\.?|County|Parish|Par\.?)\s*,?\s*"
    r"(?P<state>[A-Z]{2})\b"
)

# Parenthetical content
PAREN_RE = re.compile(r"\(([^)]+)\)")

# Words that strongly suggest the thread is NOT a clone description.
# Kept conservative — better to over-include in clone-candidate and let
# Mike filter than to drop legitimate clone titles.
NON_CLONE_HINTS = (
    "for sale", "sale!", " trade ", "auction", "giveaway", "wanted",
    "looking for ", "free to ", "now available", "offering ",
    "happy birthday", "happy new year", "merry christmas",
    "thanks", "thank you", "rip ", "in memory of",
    "monthly contest", "photo contest", "plant of the month",
    "monthly pictures", "year in review",
)


@dataclass
class TitleExtraction:
    original_title: str
    classified: str  # "clone-candidate" | "other"
    genus: Optional[str] = None
    species: Optional[str] = None
    infraspecific_rank: Optional[str] = None  # "var." | "ssp." | "f." | "x" | None
    infraspecific_name: Optional[str] = None
    cultivar: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    parenthetical: Optional[str] = None
    notes: list[str] = field(default_factory=list)


def parse_title(title: str) -> TitleExtraction:
    t = title.strip()
    if not t:
        return TitleExtraction(original_title=title, classified="other")

    lower = t.lower()
    if any(h in lower for h in NON_CLONE_HINTS):
        return TitleExtraction(original_title=title, classified="other")

    # Genus
    genus = None
    for canonical, pattern in GENUS_PATTERNS:
        if pattern.search(t):
            genus = canonical
            break

    if genus is None:
        return TitleExtraction(original_title=title, classified="other")

    # Sarracenia species (only attempt when genus is Sarracenia or "S.")
    species = None
    if genus == "Sarracenia":
        # Find first lowercase word after the genus marker that's in our
        # species list. Allow optional ssp.) prefix style "purp.venosa".
        # Strategy: tokenize on non-alpha, scan tokens.
        tokens = re.findall(r"[a-zA-Z]+", t)
        # Skip tokens that ARE the genus marker
        for tok in tokens:
            tok_l = tok.lower()
            if tok_l in {"s", "sarracenia"}:
                continue
            if tok_l in SARRACENIA_SPECIES:
                species = tok_l
                break

    # Infraspecific
    infra_rank = None
    infra_name = None
    m = INFRA_RE.search(t)
    if m:
        rank = m.group("rank").lower()
        # Normalize × / x in hybrid notation
        if rank in {"x", "×"}:
            infra_rank = "x"
        elif rank in {"subsp.", "ssp."}:
            infra_rank = "ssp."
        elif rank in {"forma", "f."}:
            infra_rank = "f."
        else:
            infra_rank = rank
        infra_name = m.group("name").lower()

    # Cultivar (single quotes)
    cultivar = None
    cm = CULTIVAR_RE.search(t)
    if cm:
        cultivar = cm.group(1).strip()

    # Location
    county = None
    state = None
    cm2 = COUNTY_RE.search(t)
    if cm2:
        candidate_state = cm2.group("state")
        if candidate_state in STATE_CODES:
            state = candidate_state
            county = cm2.group("county").strip().rstrip(",").strip()

    # Parenthetical extras
    paren = None
    pm = PAREN_RE.search(t)
    if pm:
        paren = pm.group(1).strip()

    notes = []
    if genus == "Sarracenia" and species is None:
        notes.append("genus Sarracenia detected but species not recognized")

    return TitleExtraction(
        original_title=title,
        classified="clone-candidate",
        genus=genus,
        species=species,
        infraspecific_rank=infra_rank,
        infraspecific_name=infra_name,
        cultivar=cultivar,
        county=county,
        state=state,
        parenthetical=paren,
        notes=notes,
    )
