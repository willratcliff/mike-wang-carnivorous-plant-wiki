"""Generate per-cultivar VFT wiki entries with proper photo attribution.

Reads parsed thread JSONs and walks each post's body_html, splitting on
<img> tags. The text BEFORE each image (since the previous image, or
post start) is the photo's caption-context. We attribute the image to
whichever cultivar is mentioned in that context, but only if exactly
one cultivar is mentioned — multi-cultivar contexts get skipped.

This fixes the original bug where photos were mass-assigned to every
cultivar mentioned anywhere in the post.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
manifest = json.loads((ROOT / "data" / "images" / "manifest.json").read_text())
url_to_local = {url: meta["local_path"] for url, meta in manifest.items() if meta.get("status") == "ok"}

# Cultivar definitions: slug, display name, sales id, regex patterns.
# Pattern is matched against the text-before-img to determine attribution.
CULTIVARS = [
    ("b-52",            "B-52",                  "D4",  [r'\bB[\s-]*52\b']),
    ("royal-red",       "Royal Red",             "D19", [r'\bRoyal\s*Red\b']),
    ("ginormous",       "GINORMOUS",             "D15", [r'\bGINORMOUS\b', r'\bGinormous\b']),
    ("big-mouth",       "Big Mouth",             "D3",  [r'\bBig\s*Mouth\b']),
    ("g-17-megatraps",  "G-17 MEGATRAPS",        "D13", [r'\bG[\s-]*17\b', r'MEGATRAPS']),
    ("dcxl",            "DCXL",                  "D38", [r'\bDCXL\b']),
    ("maroon-monster",  "Maroon Monster",        "D17", [r'Maroon\s*Monster']),
    ("sd-draco",        "SD Draco",              "D23", [r'\bSD[\s-]*Draco\b', r'\bDraco\b']),
    ("sd-kronos",       "SD Kronos",             "D24", [r'\bSD[\s-]*Kronos\b', r'\bKronos\b']),
    ("big-tomato",      "Big Tomato",            "D37", [r'\bBig\s*Tomato\b']),
    ("la-grosse-a-gui-gui", "La Grosse à Gui-Gui","D25",[r"Grosse|Gui-?Gui|Guigui"]),
    ("giant-clam",      "GIANT CLAM",            "D29", [r'GIANT\s*CLAM|Giant\s*Clam']),
    ("wolverine",       "Wolverine",             "D27", [r'\bWolverine\b']),
    ("schuppensteil-i", "Schuppensteil I",       "D31", [r'Schuppensteil']),
    ("alien",           "Alien",                 "D34", [r'\bAlien\b']),
    ("spotty",          "Spotty",                "D21", [r'\bSpotty\b']),
    ("low-giant",       "Low Giant",             "D16", [r'\bLow\s*Giant\b']),
    ("colorado-giant",  "Colorado Giant",        "D14", [r'Colorado\s*Giant']),
    ("g-14-rosette",    "G-14 rosette",          "D11", [r'\bG[\s-]*14\b']),
    ("tc-clone",        "TC clone",              "D1",  [r'TC\s*clone']),
    ("g-16-slacks-giant","G-16 Slack's Giant",   "D12", [r"G[\s-]*16", r"Slack.{1,4}Giant"]),
    ("coquillage",      "Coquillage",            "D33", [r'Coquillage']),
    ("red-dragon",      "Red Dragon",            "D18", [r'Red\s*Dragon']),
    ("rg38n",           "RG38N",                 "D2",  [r'RG[\s-]*38\s*N|RG38']),
]
SLUG_TO_CULTIVAR = {c[0]: c for c in CULTIVARS}

# Per-cultivar editorial notes. Same as before.
EDITORIAL = {
    "b-52": (
        "One of Mike's foundational VFT clones — present since 2015 and a "
        "consistent strong performer year after year in outdoor Northern "
        "California cultivation. Famous as one of the first widely-distributed "
        "giant clones in the hobby.",
        ["Reliable producer of large traps under outdoor culture",
         "Vigorous and clumping; one of the easier giant clones",
         "Consistent year-over-year performance in Mike's collection since 2015"]),
    "royal-red": (
        "Mike's standout red flytrap — features deep red coloration across the "
        "entire plant. Strong outdoor performer that produces tall summer "
        "traps without rosetting.",
        ["Deep red coloration across the entire plant, not just trap interior",
         "Tall upright summer traps — Mike: 'never saw it produce rosettes'",
         "Long-time favorite red — Maroon Monster is a close second"]),
    "ginormous": (
        "GINORMOUS lives up to its name once established — Mike notes this "
        "clone had a reputation for being difficult and 'over-hyped,' but in "
        "his experience it produces some of the largest traps in the collection.",
        ["Among the largest-trap clones once established",
         "Reputation for being slow/difficult — Mike disagrees once acclimated",
         "Strong producer year after year"]),
    "big-mouth": (
        "Mike was initially skeptical — Big Mouth didn't perform under outdoor "
        "Northern California conditions for several years. After about three "
        "years of establishment it took off and now produces characteristic "
        "wide-mouth traps reliably.",
        ["Slow to establish under outdoor Northern CA — needed ~3 years",
         "Distinctive wide trap morphology once mature",
         "Not as easy as B-52, but rewarding once acclimated"]),
    "g-17-megatraps": (
        "Started as a single mature bulb from Carnivero (Drew Martinez) and "
        "grew into a vigorous clone over the course of one season. One of "
        "the larger-trap clones in Mike's collection.",
        ["Strong vigor — single-bulb division established within one season",
         "Source: Carnivero (Drew Martinez)",
         "Large trap size; competes with the named giant clones"]),
    "dcxl": (
        "Drew Martinez's giant clone — originally underperformed in some "
        "growers' hands but Mike has documented it producing massive traps "
        "in his outdoor culture. One of the standout giants of the recent "
        "wave of new flytrap clones.",
        ["Massive trap production once established",
         "Some growers reported initial difficulty — establishment time matters",
         "Well-documented in Mike's collection from 2022 onward"]),
    "maroon-monster": (
        "Mike's quickly-becoming-second-favorite red flytrap behind Royal Red. "
        "Maroon Monster typically produces solid red traps under good light; "
        "in shade it shows a green-and-red mix.",
        ["Solid red traps under full sun; greener in shade",
         "Climbing to second place among Mike's reds (after Royal Red)",
         "Strong color saturation across the entire pitcher"]),
    "sd-draco": (
        "An eye-catching clone that 'steals the show' in Mike's October 2022 "
        "update. Strong vigor and distinctive trap morphology.",
        ["Standout looks — Mike: 'SD Draco steals the show' (2022-10)",
         "Produces large traps later in the season",
         "Distinctive among the recent wave of new clones"]),
    "sd-kronos": (
        "Mike's repeated praise — vigorous, easy to grow, with long cilia "
        "and good overall looks.",
        ["Vigorous and easy to grow",
         "Long cilia ('teeth')",
         "Good overall trap proportions"]),
    "big-tomato": (
        "Mike was unimpressed at first but the clone improved markedly as it "
        "colored up across the season. Distinctive rounded trap shape and "
        "deep red coloration.",
        ["Color improves significantly through the season",
         "Distinctive rounded ('tomato') trap morphology",
         "Underrated initially — better than first impressions suggest"]),
    "la-grosse-a-gui-gui": (
        "French giant cultivar. Mike's specimens haven't reached the maximum "
        "documented size yet, but the clone is well-represented across his "
        "2022-2023 documentation showing steady growth.",
        ["French-origin giant",
         "Mike's plants still maturing — others have grown larger specimens",
         "Vigorous once established"]),
    "giant-clam": (
        "True to its name — produces unusually rounded, clam-shell-shaped "
        "traps with distinctive opening morphology.",
        ["Distinctive clam-shell trap shape",
         "Unusual opening / hinge morphology",
         "Well-documented in Mike's 2022-2024 photos"]),
    "wolverine": (
        "A vigorous and productive clone Mike has been documenting since "
        "2022. Solid trap production with characteristic markings.",
        ["Strong vigor in outdoor Northern CA culture",
         "Consistent producer across multiple seasons",
         "Distinctive coloration"]),
    "schuppensteil-i": (
        "Distinctive 'scaly stem' trait — Mike's pictures from 2022-2026 "
        "consistently show the unusual petiole texture that gives this "
        "cultivar its German name.",
        ["Distinctive scaly / textured petiole ('Schuppensteil' = scaly stem)",
         "German-origin selection",
         "Visually unusual within the broader VFT cultivar range"]),
    "alien": (
        "Mike's mother plants of Alien show a distinctive trap profile. "
        "Established in his collection from 2022 onward.",
        ["Distinctive trap profile",
         "Established in Mike's collection since 2022",
         "Recurring in collection-overview photo series"]),
    "spotty": (
        "Variable variegation — Mike documented Spotty as variegated earlier "
        "in 2024 but reverted to green/red later that season.",
        ["Variegation can revert under outdoor culture (Mike, 2024)",
         "Otherwise vigorous and well-formed traps",
         "Distinctive when variegation expresses"]),
    "low-giant": (
        "Mike chased this clone for years before sourcing one from Matt "
        "Miller (flytrapcare.com) in June 2021. The 'low' refers to its "
        "compact growth habit; the 'giant' refers to the trap size.",
        ["Compact growth habit, oversized traps",
         "Source: Matt Miller / flytrapcare.com (2021)",
         "Mike pursued this clone for years — finally acquired 2021"]),
    "colorado-giant": (
        "Mike's documentation captures the plant during winter dormancy — "
        "the smaller dormant traps are a striking contrast to its peak-season "
        "size.",
        ["Large traps in peak season",
         "Dormant-season photos show characteristic compact form",
         "Established for multiple seasons in Mike's collection"]),
    "g-14-rosette": (
        "Originally known as G-14 with a rosetted growth pattern (alexis on "
        "the forum, 2021: actually G-14 × G-4 per known lineage). Stays low "
        "and produces traps in a tight rosette.",
        ["Rosetted (low, ground-hugging) growth pattern",
         "Lineage: likely G-14 × G-4 per alexis (forum post 2021)",
         "Consistent year-over-year performance"]),
    "tc-clone": (
        "Mike's working label for a tissue-cultured clone of unknown origin "
        "that has been in his collection since the 1990s — predates most of "
        "the named cultivar boom.",
        ["Mike's longest-held VFT clone (1990s acquisition)",
         "Vigorous; decent-sized but not giant traps",
         "Source: tissue culture, exact origin unrecorded"]),
    "g-16-slacks-giant": (
        "Adrian Slack's 'Slack's Giant' under its G-16 designation. One of "
        "the older named giants in the hobby; in Mike's giant-clone "
        "comparison group.",
        ["Adrian Slack's named giant cultivar",
         "Part of Mike's giant-clone benchmark group",
         "Reliable performer across multiple seasons"]),
    "coquillage": (
        "Coquillage produced two flower spikes in spring 2022; Mike pinched "
        "them early to direct energy back into vegetative growth. Distinctive "
        "trap morphology with characteristic shell-like appearance.",
        ["Shell-like trap morphology",
         "Two spring 2022 flower spikes — Mike pinched both",
         "French-origin selection"]),
    "red-dragon": (
        "A red-trap clone with strong color expression. Mike's photos show "
        "deep red coloration developing across the season.",
        ["Deep red trap coloration",
         "Featured alongside other red selections in Mike's comparison photos",
         "Develops color through the season"]),
    "rg38n": (
        "Mike's tongue-in-cheek explanation: people thought RG38N stood for "
        "'Real Gangster at 38° North Latitude' — it does not. The actual "
        "origin is unrecorded, but the clone produces solid red color and "
        "distinctive trap morphology.",
        ["Solid red trap interiors",
         "Mike's documentation 2024-2025; relatively new to his collection",
         "Cryptic name — Mike has joked about the meaning (post 51123, 2025-02)"]),
}


def img_attribution(body_html: str, image_urls: list[str]) -> dict[str, str | None]:
    """Walk body_html in order; for each <img>, return the cultivar slug
    based on the text-since-previous-img. None if 0 or >1 cultivars are
    mentioned in that context (ambiguous → drop).
    """
    if not body_html:
        return {u: None for u in image_urls}

    # Split body_html by <img>, but keep image src so we can match.
    parts = re.split(r'<img[^>]*src="([^"]+)"[^>]*/?>', body_html)
    # parts looks like [text0, src0, text1, src1, text2, ...]
    texts_before_img = []
    img_srcs = []
    accumulated_text = ""
    for i, part in enumerate(parts):
        if i % 2 == 0:
            accumulated_text += part
        else:
            img_srcs.append(part)
            texts_before_img.append(accumulated_text)
            accumulated_text = ""

    result: dict[str, str | None] = {}
    for src, ctx in zip(img_srcs, texts_before_img):
        # Strip HTML tags from ctx
        plain = re.sub(r'<[^>]+>', ' ', ctx)
        # Find which cultivars match
        matches = []
        for slug, _name, _sid, pats in CULTIVARS:
            if any(re.search(p, plain, re.I) for p in pats):
                matches.append(slug)
        # Special-case: 'Big Mouth' substring matches 'Big' inside 'Big Tomato'
        # (the other way around is fine because Big Tomato is more specific).
        # Resolve by preferring the most specific name when both match.
        if "big-mouth" in matches and "big-tomato" in matches:
            # Whichever appears later in the context likely owns the photo —
            # but easier: drop both as ambiguous.
            pass
        # G-14 also matches G-14, G-16, G-17 substrings; the regex is bounded so
        # it's OK as long as the patterns are bounded. Already are.
        # Same for GIANT CLAM vs Low Giant — both have "Giant"; patterns are
        # bounded so distinct.
        if len(matches) == 1:
            result[src] = matches[0]
        else:
            result[src] = None  # ambiguous or no match → unattributed
    # For any URL that wasn't in body_html (rare), set None
    for u in image_urls:
        if u not in result:
            result[u] = None
    return result


def collect_cultivar_photos():
    """For each cultivar, return list of (post_id, thread, date, url, local).
    Walks all relevant threads and uses inline-image attribution.
    """
    results: dict[str, list[dict]] = {slug: [] for slug, *_ in CULTIVARS}
    for thread in [2459, 673, 940, 2807, 2534, 824, 3170]:
        files = sorted(glob.glob(str(ROOT / f"data/parsed/threads/{thread}/page-*.json")))
        for f in files:
            d = json.loads(Path(f).read_text())
            for p in d["posts"]:
                # Only count Mike's own posts
                if p["author_username"] not in ("meizzwang",):
                    continue
                attribution = img_attribution(p.get("body_html", ""), p["image_urls"])
                for u in p["image_urls"]:
                    cult = attribution.get(u)
                    if not cult:
                        continue
                    local = url_to_local.get(u)
                    if not local:
                        continue
                    results[cult].append({
                        "post_id": p["post_id"],
                        "thread": thread,
                        "date": p["timestamp_iso"][:10],
                        "url": u,
                        "local": local,
                    })
    return results


def build_entry(slug: str, cultivar: tuple, photos: list[dict]) -> str:
    _slug, name_short, _sid, _pats = cultivar
    summary, traits = EDITORIAL[slug]
    full_name = f"Dionaea muscipula '{name_short}'"

    photo_lines = []
    for i, p in enumerate(photos):
        favorite = (i == 0)
        cap = f"{name_short}, {p['date']}"
        if favorite:
            cap = f"{name_short} (hero), {p['date']}"
        photo_lines.append(
            f'  - {{ path: "{p["local"]}", caption: "{cap}", '
            f'photographer: "Mike Wang", source_post_id: {p["post_id"]}, '
            f'favorite: {"true" if favorite else "false"} }}'
        )
    photos_block = "\n".join(photo_lines) if photo_lines else "[]"

    threads_seen: dict[int, str] = {}
    for p in photos:
        if p["thread"] not in threads_seen:
            threads_seen[p["thread"]] = "primary" if not threads_seen else "context"
    thread_lines = []
    for tid, role in threads_seen.items():
        thread_url = {
            2459: "https://sarracenia.proboards.com/thread/2459/grow-report-various-different-venus",
            673: "https://sarracenia.proboards.com/thread/673/darlingtonia-californica-cobra-plant-pics",
            2534: "https://sarracenia.proboards.com/thread/2534/dionaea-ortons-red-side",
            3170: "https://sarracenia.proboards.com/thread/3170/california-carnivores-venus-fly-trap",
        }.get(tid, f"https://sarracenia.proboards.com/thread/{tid}/")
        thread_lines.append(f"""  - thread_id: {tid}
    url: "{thread_url}"
    role: "{role}\"""")
    thread_block = "\n".join(thread_lines) if thread_lines else "[]"

    traits_block = "\n".join(f'  - "{t}"' for t in traits)

    cult_field = name_short.replace("'", "''")  # YAML quote escaping

    year = photos[0]["date"][:4] if photos else 2015

    return f"""---
full_name: "{full_name}"
short_name: "{name_short}"
genus: "Dionaea"
species: "muscipula"
infraspecific_rank: null
infraspecific_name: null
hybrid: false
cultivar: "{cult_field}"
cultivar_group: null
accession_type: "named-cultivar"

origin_locality:
  county: null
  state: null
  country: null
  notes: "Cultivar — origin not localized. Mike's plants from various sources documented in source threads."
collector: null
breeder: null
year_collected: null
year_into_cultivation: null
year_first_described_on_forum: {year}

standout_traits:
{traits_block}

visually_similar_to: []

cultivation_notes: |
  Outdoor Northern California cultivation. Standard Dionaea muscipula
  requirements: full sun, distilled/RO water, dormant winter rest.
  See Mike's individual post observations for clone-specific timing.

source_threads:
{thread_block}

photos:
{photos_block}

review:
  ai_extracted_by: "Claude (Claude Code session, 2026-05-08)"
  ai_extracted_at: "2026-05-08T00:00:00Z"
  human_reviewed: false
  human_reviewer: null
  human_corrections: []
  open_questions: []
---

# {full_name}

{summary}
"""


def main():
    photos_by_cult = collect_cultivar_photos()
    out_root = ROOT / "wiki" / "dionaea"

    written = []
    skipped = []
    for cult in CULTIVARS:
        slug = cult[0]
        photos = photos_by_cult.get(slug, [])
        if not photos:
            skipped.append((slug, "no attributable photos"))
            continue
        out_dir = out_root / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        text = build_entry(slug, cult, photos)
        (out_dir / "index.md").write_text(text)
        written.append((slug, len(photos)))

    print(f"wrote {len(written)} entries:")
    for slug, n in written:
        print(f"  {slug:24s}  {n} photo(s)")
    if skipped:
        print(f"\nskipped {len(skipped)}:")
        for slug, reason in skipped:
            print(f"  {slug}: {reason}")


if __name__ == "__main__":
    main()
