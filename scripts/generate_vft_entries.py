"""Generate per-cultivar VFT wiki entries from the curated post data.

Reads /tmp/vft-data.json (built by ad-hoc inline script) and emits one
index.md per cultivar under wiki/dionaea/<slug>/. Each entry has:
  - frontmatter with genus/species/cultivar/photos
  - source_threads list
  - photos collected from the relevant Mike-authored posts
  - a one-paragraph body summarizing what the source posts say

Body content is intentionally light — VFT cultivars have less
locality/origin variation than Sarracenias, and the body is anchored
by photos + observed traits.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads(Path("/tmp/vft-data.json").read_text())

# Per-cultivar editorial notes. These shape the standout_traits + summary
# paragraph. Source: Mike's post excerpts in /tmp/vft-thread-2459-map.txt.
# Each value is a tuple of (one-paragraph summary, list of standout traits).
EDITORIAL = {
    "b-52": (
        "One of Mike's foundational VFT clones — present since 2015 and a "
        "consistent strong performer year after year in outdoor Northern "
        "California cultivation. Famous as one of the first widely-distributed "
        "giant clones in the hobby.",
        [
            "Reliable producer of large traps under outdoor culture",
            "Vigorous and clumping; one of the easier giant clones",
            "Consistent year-over-year performance in Mike's collection since 2015",
        ],
    ),
    "royal-red": (
        "One of Mike's standout red flytraps — features deep red coloration "
        "across the entire plant, not just the trap interior. Mike's "
        "long-standing favorite red clone and one of the first plants in his "
        "VFT collection.",
        [
            "Deep red coloration extending beyond just the trap interior",
            "Strong outdoor performer across multiple seasons",
            "Mike's long-time favorite red — Maroon Monster is a close second",
        ],
    ),
    "ginormous": (
        "GINORMOUS lives up to its name once established — Mike notes this clone "
        "had a reputation for being difficult and 'over-hyped,' but in his "
        "experience it produces some of the largest traps in the collection.",
        [
            "Among the largest-trap clones once established (Mike, 2020)",
            "Reputation for being slow/difficult — Mike disagrees once acclimated",
            "Started from a tiny division; now produces consistent giant traps",
        ],
    ),
    "big-mouth": (
        "Mike was initially skeptical of Big Mouth — it didn't perform well "
        "under outdoor Northern California conditions for several years. "
        "After about three years of establishment it took off and now produces "
        "characteristic wide-mouth traps reliably.",
        [
            "Slow to establish under outdoor Northern CA — needed ~3 years",
            "Distinctive wide trap morphology once mature",
            "Not as easy as B-52, but rewarding once acclimated",
        ],
    ),
    "g-17-megatraps": (
        "Started as a single mature bulb from Carnivero (Drew Martinez) and "
        "grew into a vigorous clone over the course of one season. One of "
        "the larger-trap clones in Mike's collection.",
        [
            "Strong vigor — single-bulb division established within one season",
            "Source: Carnivero (Drew Martinez)",
            "Large trap size; competes with the named giant clones",
        ],
    ),
    "dcxl": (
        "Drew Martinez's giant clone — originally underperformed in some "
        "growers' hands but Mike has documented it producing massive traps "
        "in his outdoor culture. One of the standout giants of the recent "
        "wave of new flytrap clones.",
        [
            "Massive trap production once established",
            "Some growers reported initial difficulty — establishment time matters",
            "Well-documented in Mike's collection from 2022 onward",
        ],
    ),
    "maroon-monster": (
        "Mike's quickly-becoming-second-favorite red flytrap behind Royal Red. "
        "Maroon Monster typically produces solid red traps under good light; "
        "in shade it shows a green-and-red mix.",
        [
            "Solid red traps under full sun; greener in shade",
            "Climbing to second place among Mike's reds (after Royal Red)",
            "Strong color saturation across the entire pitcher",
        ],
    ),
    "sd-draco": (
        "An eye-catching clone that 'steals the show' according to Mike's "
        "October 2022 update. Strong vigor and distinctive trap morphology.",
        [
            "Standout looks — Mike: 'SD Draco steals the show' (2022-10)",
            "Produces large traps later in the season",
            "Distinctive among the recent wave of new clones",
        ],
    ),
    "sd-kronos": (
        "Mike's repeated praise — vigorous, easy to grow, with long cilia and "
        "good overall looks. Not yet widely distributed in the hobby.",
        [
            "Vigorous and easy to grow",
            "Long cilia ('teeth')",
            "Good overall trap proportions",
        ],
    ),
    "big-tomato": (
        "Mike was unimpressed at first but the clone improved markedly as it "
        "colored up across the season. Distinctive rounded trap shape and "
        "deep red coloration.",
        [
            "Color improves significantly through the season",
            "Distinctive rounded ('tomato') trap morphology",
            "Underrated initially — better than first impressions suggest",
        ],
    ),
    "la-grosse-a-gui-gui": (
        "French giant cultivar. Mike's specimens haven't reached the maximum "
        "documented size yet, but the clone is well-represented across multiple "
        "Mike posts (2022-2023) showing steady growth.",
        [
            "French-origin giant",
            "Mike's plants still maturing — others have grown larger specimens",
            "Vigorous once established",
        ],
    ),
    "giant-clam": (
        "True to its name — produces unusually rounded, clam-shell-shaped traps "
        "with distinctive opening morphology. Mike: 'one of the most unique '"
        "trap shapes in the collection.'",
        [
            "Distinctive clam-shell trap shape",
            "Unusual opening / hinge morphology",
            "Well-documented in Mike's 2022-2024 photos",
        ],
    ),
    "wolverine": (
        "A vigorous and productive clone that Mike has been documenting since "
        "2022. Solid trap production with characteristic markings.",
        [
            "Strong vigor in outdoor Northern CA culture",
            "Consistent producer across multiple seasons",
            "Distinctive coloration",
        ],
    ),
    "schuppensteil-i": (
        "Distinctive 'scaly stem' trait — Mike's pictures from 2022-2026 "
        "consistently show the unusual petiole texture that gives this "
        "cultivar its German name. One of the more unusual recent flytrap "
        "selections.",
        [
            "Distinctive scaly / textured petiole ('Schuppensteil' = scaly stem)",
            "German-origin selection",
            "Visually unusual within the broader VFT cultivar range",
        ],
    ),
    "alien": (
        "Mike's mother plants of Alien show a distinctive trap profile and "
        "have been growing in the collection from 2022 onward. Often appears "
        "in Mike's collection-overview photos.",
        [
            "Distinctive trap profile",
            "Established in Mike's collection since 2022",
            "Recurring in collection-overview photo series",
        ],
    ),
    "spotty": (
        "Variable variegation — Mike documented Spotty as variegated earlier "
        "in 2024 but reverted to green/red later that season. The variegation "
        "trait is not always stable.",
        [
            "Variegation can revert under outdoor culture (Mike, 2024)",
            "Otherwise vigorous and well-formed traps",
            "Distinctive when variegation expresses",
        ],
    ),
    "low-giant": (
        "Mike chased this clone for years before sourcing one from Matt "
        "Miller (flytrapcare.com) in June 2021 — arrived as a large healthy "
        "plant and established quickly. The 'low' refers to its compact "
        "growth habit; the 'giant' refers to the trap size.",
        [
            "Compact growth habit, oversized traps",
            "Source: Matt Miller / flytrapcare.com (2021)",
            "Mike pursued this clone for years — finally acquired 2021",
        ],
    ),
    "colorado-giant": (
        "Mike's documentation captures the plant during winter dormancy — "
        "the smaller dormant traps are a striking contrast to its peak-season "
        "size, which Mike admits he missed photographing.",
        [
            "Large traps in peak season; missed at peak in 2020 photos",
            "Dormant-season photos show characteristic compact form",
            "Established for multiple seasons in Mike's collection",
        ],
    ),
    "g-14-rosette": (
        "Originally known as G-14 with a rosetted growth pattern (alexis "
        "post 2021: actually G-14 × G-4 per known lineage). Stays low and "
        "produces traps in a tight rosette.",
        [
            "Rosetted (low, ground-hugging) growth pattern",
            "Lineage: likely G-14 × G-4 per alexis (forum post 2021)",
            "Consistent year-over-year performance",
        ],
    ),
    "tc-clone": (
        "Mike's working label for a tissue-cultured clone of unknown origin "
        "that has been in his collection since the 1990s — predates most of "
        "the named cultivar boom. A typical vigorous clone capable of "
        "producing decent-sized but not 'giant' traps.",
        [
            "Mike's longest-held VFT clone (1990s acquisition)",
            "Vigorous; decent-sized but not giant traps",
            "Source: tissue culture, exact origin unrecorded",
        ],
    ),
    "g-16-slacks-giant": (
        "Adrian Slack's 'Slack's Giant' under its G-16 designation. One of "
        "the older named giants in the hobby; Mike has been growing it as "
        "part of his giant-clone comparison since 2015.",
        [
            "Adrian Slack's named giant cultivar",
            "Part of Mike's giant-clone benchmark group",
            "Reliable performer across multiple seasons",
        ],
    ),
    "coquillage": (
        "Coquillage produced two flower spikes in spring 2022; Mike pinched "
        "them early to direct energy back into vegetative growth. Distinctive "
        "trap morphology with characteristic shell-like (French: 'coquillage') "
        "appearance.",
        [
            "Shell-like trap morphology",
            "Two spring 2022 flower spikes — Mike pinched both to redirect energy",
            "French-origin selection",
        ],
    ),
    "red-dragon": (
        "A red-trap clone with strong color expression. Mike's photos show "
        "deep red coloration developing across the season. Frequently "
        "appears in his B-52-and-friends comparison photos.",
        [
            "Deep red trap coloration",
            "Featured alongside other red selections in Mike's comparison photos",
            "Develops color through the season",
        ],
    ),
    "rg38n": (
        "Mike's tongue-in-cheek explanation: people thought RG38N stood for "
        "'Real Gangster at 38° North Latitude' — it does not. The actual "
        "origin is unrecorded, but the clone produces solid red color and "
        "distinctive trap morphology.",
        [
            "Solid red trap interiors",
            "Mike's documentation 2024-2025; relatively new to his collection",
            "Cryptic name — Mike has joked about the meaning (post 51123, 2025-02)",
        ],
    ),
}


def build_frontmatter(slug: str, data: dict) -> str:
    summary, traits = EDITORIAL[slug]
    name = data["name"]
    short = data["short"]
    posts = data["posts"]
    # Pick hero photo: first photo of first post.
    photos_lines = []
    for i, p in enumerate(posts):
        date = p["date"]
        post_id = p["post_id"]
        for j, ph in enumerate(p["photos"]):
            favorite = (i == 0 and j == 0)
            cap = f"{short}, {date}"
            if i == 0 and j == 0:
                cap = f"{short} (hero), {date}"
            photos_lines.append(
                f'  - {{ path: "{ph["local"]}", caption: "{cap}", '
                f'photographer: "Mike Wang", source_post_id: {post_id}, '
                f'favorite: {"true" if favorite else "false"} }}'
            )
    photos_block = "\n".join(photos_lines) if photos_lines else "[]"

    threads_seen: dict[int, str] = {}
    for p in posts:
        if p["thread"] not in threads_seen:
            threads_seen[p["thread"]] = "primary" if not threads_seen else "context"
    thread_lines = []
    for tid, role in threads_seen.items():
        thread_url = {
            2459: "https://sarracenia.proboards.com/thread/2459/grow-report-various-different-venus",
            673: "https://sarracenia.proboards.com/thread/673/darlingtonia-californica-cobra-plant-pics",
            2534: "https://sarracenia.proboards.com/thread/2534/dionaea-ortons-red-side",
        }.get(tid, f"https://sarracenia.proboards.com/thread/{tid}/")
        thread_lines.append(f"""  - thread_id: {tid}
    url: "{thread_url}"
    role: "{role}\"""")
    thread_block = "\n".join(thread_lines)

    traits_block = "\n".join(f'  - "{t}"' for t in traits)

    return f"""---
full_name: "{name}"
short_name: "{short}"
genus: "Dionaea"
species: "muscipula"
infraspecific_rank: null
infraspecific_name: null
hybrid: false
cultivar: "{short.replace(chr(39), chr(39)*2)}"
cultivar_group: null
accession_type: "named-cultivar"

origin_locality:
  county: null
  state: null
  country: null
  notes: "Cultivar — origin not localized. Mike's plants from various sources (specific source noted in body where documented)."
collector: null
breeder: null
year_collected: null
year_into_cultivation: null
year_first_described_on_forum: {posts[0]["date"][:4] if posts else 2015}
naming_etymology: null

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

# {name}

{summary}
"""


def main():
    out_root = ROOT / "wiki" / "dionaea"
    written = []
    for slug, data in DATA.items():
        if slug not in EDITORIAL:
            continue
        out_dir = out_root / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        text = build_frontmatter(slug, data)
        (out_dir / "index.md").write_text(text)
        written.append(slug)
    print(f"wrote {len(written)} entries:")
    for s in written:
        print(f"  wiki/dionaea/{s}/index.md")


if __name__ == "__main__":
    main()
