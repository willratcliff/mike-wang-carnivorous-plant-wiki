"""Static-site generator for the wiki.

Reads:  wiki/<genus>/<species>/.../index.md (Markdown with YAML frontmatter)
        data/images/<sha-prefix>/<sha>.<ext>
Writes: _site/<same-tree>/index.html
        _site/index.html         (top-level: genera + recently-added)
        _site/<genus>/index.html (per-genus index: species list)
        _site/<genus>/<species>/index.html (per-species: clone list)
        _site/images/...         (copied from data/images)
        _site/static/style.css

Each clone page renders:
- Identity header
- A "REVIEW STATUS" banner if not human-reviewed (always-visible
  per Mike's decision)
- Origin / History / Standout traits / Cultivation notes (Markdown body)
- Photo gallery, captions visible, all images served locally
- Source threads with links to the proboards URLs
- [VERIFY] / [MISSING] / open_questions surfaced in a sidebar so a
  reviewer can find them at a glance

The generator is conservative: any page that doesn't have valid YAML
frontmatter is skipped with a warning rather than crashed on. The
build is reproducible — outputs are deterministic given the inputs.
"""

from __future__ import annotations

import datetime as dt
import html
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import markdown as md_lib
import yaml
from jinja2 import Environment, BaseLoader, select_autoescape

LOG = logging.getLogger("sarrwiki.site")

VERIFY_RE = re.compile(r"\[VERIFY\]")
MISSING_RE = re.compile(r"\[MISSING\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


# ----------------------------------------------------------------------
# Templates (kept inline so the site gen is one file)
# ----------------------------------------------------------------------

CSS = """\
:root {
  --fg: #1a1a1a;
  --muted: #666;
  --accent: #2a6f4a;
  --accent-bg: #f0f7f3;
  --warn: #b15a00;
  --warn-bg: #fff5e6;
  --missing: #b00020;
  --missing-bg: #fff0f2;
  --border: #ddd;
  --bg: #fafaf7;
  --card-bg: #fff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  color: var(--fg);
  background: var(--bg);
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header.site {
  background: var(--accent);
  color: #fff;
  padding: 12px 24px;
}
header.site a { color: #fff; }
header.site h1 { margin: 0; font-size: 18px; font-weight: 600; }
.crumbs { font-size: 13px; opacity: 0.85; margin-top: 2px; }
main { max-width: 1100px; margin: 0 auto; padding: 24px; }
.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px 20px;
  margin-bottom: 24px;
}
.review-banner {
  background: var(--warn-bg);
  border: 1px solid var(--warn);
  color: var(--warn);
  padding: 10px 14px;
  border-radius: 4px;
  margin-bottom: 24px;
  font-size: 14px;
}
.review-banner strong { color: var(--warn); }
.identity {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 16px;
  font-size: 14px;
  margin-bottom: 16px;
}
.identity dt { color: var(--muted); }
.identity dd { margin: 0; }
.gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
  margin: 16px 0;
}
.gallery figure { margin: 0; background: #fff; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.gallery img { display: block; width: 100%; height: auto; }
.gallery figcaption { padding: 8px 10px; font-size: 13px; color: var(--muted); }
.body-content h1, .body-content h2, .body-content h3 { margin-top: 24px; }
.body-content h1 { font-size: 24px; }
.body-content h2 { font-size: 20px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.body-content h3 { font-size: 16px; }
.body-content blockquote { color: var(--muted); border-left: 3px solid var(--border); padding-left: 12px; margin-left: 0; }
.verify { background: var(--warn-bg); color: var(--warn); padding: 1px 5px; border-radius: 3px; font-size: 12px; font-weight: 600; }
.missing { background: var(--missing-bg); color: var(--missing); padding: 1px 5px; border-radius: 3px; font-size: 12px; font-weight: 600; }
.sidebar {
  background: var(--accent-bg);
  border: 1px solid var(--accent);
  border-radius: 4px;
  padding: 12px 16px;
  font-size: 14px;
  margin-bottom: 24px;
}
.sidebar h3 { margin: 0 0 8px 0; font-size: 14px; color: var(--accent); }
.sidebar ul { margin: 4px 0; padding-left: 20px; }
.sidebar li { margin: 2px 0; }
table.list { width: 100%; border-collapse: collapse; }
table.list th { text-align: left; padding: 8px 10px; background: #f4f4f4; border-bottom: 1px solid var(--border); }
table.list td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
table.list tr:hover td { background: #fafafa; }
.muted { color: var(--muted); font-size: 13px; }
footer { color: var(--muted); font-size: 13px; padding: 16px 24px; text-align: center; }
"""

LAYOUT = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }} — Carnivorous Plant Clone Wiki</title>
  <link rel="stylesheet" href="{{ root_rel }}static/style.css">
</head>
<body>
  <header class="site">
    <a href="{{ root_rel }}index.html"><h1>Carnivorous Plant Clone Wiki</h1></a>
    {% if breadcrumbs %}
    <div class="crumbs">
      {% for label, url in breadcrumbs %}
        {% if not loop.last %}<a href="{{ url }}">{{ label }}</a> ›
        {% else %}{{ label }}{% endif %}
      {% endfor %}
    </div>
    {% endif %}
  </header>
  <main>
    {{ content | safe }}
  </main>
  <footer>
    Generated {{ generated_at }} — clones described by Mike Wang on
    sarracenia.proboards.com, archived for posterity.
  </footer>
</body>
</html>
"""

CLONE_PAGE = """\
{% if not review.human_reviewed %}
<div class="review-banner">
  <strong>Review status:</strong> AI-extracted, not yet reviewed by Mike Wang.
  Items marked <span class="verify">[VERIFY]</span> are inferences;
  items marked <span class="missing">[MISSING]</span> need additional input.
</div>
{% endif %}

<div class="card">
  <h1 style="margin-top:0">{{ frontmatter.full_name or short_name }}</h1>
  <dl class="identity">
    {% if frontmatter.short_name %}<dt>Short name</dt><dd>{{ frontmatter.short_name }}</dd>{% endif %}
    <dt>Genus / species</dt><dd>
      <em>{{ frontmatter.genus }}</em>{% if frontmatter.species %} <em>{{ frontmatter.species }}</em>{% endif %}
      {% if frontmatter.infraspecific_rank %} {{ frontmatter.infraspecific_rank }} <em>{{ frontmatter.infraspecific_name }}</em>{% endif %}
    </dd>
    {% if frontmatter.cultivar_group %}<dt>Cultivar group</dt><dd>{{ frontmatter.cultivar_group }}</dd>{% endif %}
    {% if frontmatter.origin_locality and (frontmatter.origin_locality.county or frontmatter.origin_locality.state) %}
    <dt>Origin locality</dt><dd>
      {% if frontmatter.origin_locality.county %}{{ frontmatter.origin_locality.county }} Co, {% endif %}{{ frontmatter.origin_locality.state or '' }}{% if frontmatter.origin_locality.country %}, {{ frontmatter.origin_locality.country }}{% endif %}
    </dd>
    {% endif %}
    {% if frontmatter.collector %}<dt>Collector</dt><dd>{{ frontmatter.collector }}</dd>{% endif %}
    {% if frontmatter.breeder %}<dt>Breeder / selector</dt><dd>{{ frontmatter.breeder }}</dd>{% endif %}
    {% if frontmatter.year_first_described_on_forum %}<dt>First documented</dt><dd>{{ frontmatter.year_first_described_on_forum }}</dd>{% endif %}
  </dl>
</div>

{% if open_questions %}
<div class="sidebar">
  <h3>Open questions for review</h3>
  <ul>
    {% for q in open_questions %}<li>{{ q }}</li>{% endfor %}
  </ul>
</div>
{% endif %}

<div class="body-content">
{{ body_html | safe }}
</div>

{% if photos %}
<h2>Photographs</h2>
<div class="gallery">
  {% for p in photos %}
  <figure>
    {% if p.image_exists %}
    <a href="{{ image_url(p.path) }}"><img src="{{ image_url(p.path) }}" alt="{{ p.caption or '' }}"></a>
    {% else %}
    <div style="padding:40px; text-align:center; color: var(--missing); font-size: 13px;">[image missing]</div>
    {% endif %}
    {% if p.caption %}<figcaption>{{ p.caption }}{% if p.photographer %} <span class="muted">— {{ p.photographer }}</span>{% endif %}</figcaption>{% endif %}
  </figure>
  {% endfor %}
</div>
{% endif %}

{% if frontmatter.source_threads %}
<h2>Source threads</h2>
<ul>
  {% for s in frontmatter.source_threads %}
  <li><a href="{{ s.url }}">Thread {{ s.thread_id }}</a>{% if s.role %} <span class="muted">({{ s.role }})</span>{% endif %}</li>
  {% endfor %}
</ul>
{% endif %}
"""

GROUP_PAGE = """\
{% if not review.human_reviewed %}
<div class="review-banner">
  <strong>Review status:</strong> AI-extracted cultivar group, not yet reviewed by Mike Wang.
</div>
{% endif %}

<div class="card">
  <h1 style="margin-top:0">{{ frontmatter.group_name or short_name }} <span class="muted">— cultivar group</span></h1>
  <dl class="identity">
    <dt>Genus / species</dt><dd>
      <em>{{ frontmatter.genus }}</em>{% if frontmatter.species %} <em>{{ frontmatter.species }}</em>{% endif %}
      {% if frontmatter.infraspecific_rank %} {{ frontmatter.infraspecific_rank }} <em>{{ frontmatter.infraspecific_name }}</em>{% endif %}
    </dd>
  </dl>
</div>

<div class="body-content">
{{ body_html | safe }}
</div>

{% if member_clones %}
<h2>Member clones</h2>
<table class="list">
  <thead><tr><th>Clone</th><th>Status</th></tr></thead>
  <tbody>
  {% for c in member_clones %}
    <tr>
      <td><a href="{{ c.href }}">{{ c.name }}</a></td>
      <td class="muted">{% if c.reviewed %}reviewed{% else %}awaiting review{% endif %}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
"""

SPECIES_INDEX = """\
<div class="card">
  <h1 style="margin-top:0"><em>{{ genus }}</em> <em>{{ species }}</em></h1>
  <p class="muted">{{ entries | length }} clone {{ 'entry' if entries|length==1 else 'entries' }} in this archive.</p>
</div>

<table class="list">
  <thead><tr><th>Clone</th><th>Locality</th><th>First documented</th><th>Status</th></tr></thead>
  <tbody>
  {% for e in entries %}
    <tr>
      <td><a href="{{ e.href }}">{{ e.name }}</a></td>
      <td>{{ e.locality or '' }}</td>
      <td class="muted">{{ e.year or '' }}</td>
      <td class="muted">{% if e.reviewed %}reviewed{% else %}awaiting review{% endif %}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
"""

GENUS_INDEX = """\
<div class="card">
  <h1 style="margin-top:0"><em>{{ genus }}</em></h1>
  <p class="muted">{{ species_list | length }} {{ 'species' if species_list|length==1 else 'species' }} represented.</p>
</div>

<table class="list">
  <thead><tr><th>Species</th><th>Clones in archive</th></tr></thead>
  <tbody>
  {% for s in species_list %}
    <tr>
      <td><a href="{{ s.href }}"><em>{{ s.name }}</em></a></td>
      <td>{{ s.count }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
"""

ROOT_INDEX = """\
<div class="card">
  <h1 style="margin-top:0">Carnivorous Plant Clone Wiki</h1>
  <p>An archive of carnivorous plant clones described by
  <a href="https://sarracenia.proboards.com/user/11">Mike Wang</a>
  on the <a href="https://sarracenia.proboards.com">Sarracenia
  Forum</a>. {{ stats.clones }} clone {{ 'entry' if stats.clones==1 else 'entries' }} across
  {{ stats.species }} species and {{ stats.genera }} genera.</p>
  <p class="muted">Most entries are AI-extracted from forum posts and
  await review by Mike. Look for the orange banner on each page.</p>
</div>

<h2>Browse by genus</h2>
<table class="list">
  <thead><tr><th>Genus</th><th>Species</th><th>Clones</th></tr></thead>
  <tbody>
  {% for g in genera %}
    <tr>
      <td><a href="{{ g.href }}"><em>{{ g.name }}</em></a></td>
      <td>{{ g.species_count }}</td>
      <td>{{ g.clone_count }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
"""


# ----------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------


@dataclass
class WikiEntry:
    """A loaded wiki/<...>/index.md."""
    path: Path                      # absolute path to the source .md
    rel_path: Path                  # path relative to wiki/ (e.g. "sarracenia/oreophila/.../clone-a/index.md")
    type: str                       # "clone" | "cultivar_group"
    frontmatter: dict
    body_md: str
    review: dict
    open_questions: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# Loader
# ----------------------------------------------------------------------


def load_wiki_entries(wiki_root: Path) -> list[WikiEntry]:
    entries: list[WikiEntry] = []
    for path in sorted(wiki_root.rglob("index.md")):
        rel = path.relative_to(wiki_root)
        text = path.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(text)
        if not m:
            LOG.warning("no frontmatter in %s — skipping", rel)
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            LOG.warning("bad YAML in %s: %s — skipping", rel, e)
            continue
        body = m.group(2)
        etype = fm.get("type", "clone")
        review = fm.get("review", {}) or {}
        oq = (review.get("open_questions") or []) if isinstance(review, dict) else []
        entries.append(WikiEntry(
            path=path,
            rel_path=rel,
            type=etype,
            frontmatter=fm,
            body_md=body,
            review=review if isinstance(review, dict) else {},
            open_questions=oq,
        ))
    return entries


# ----------------------------------------------------------------------
# Renderers
# ----------------------------------------------------------------------


def _depth_to_root(rel_path: Path) -> str:
    # rel_path like "sarracenia/leucophylla/.../index.md"; depth = number of directories before index.md
    depth = len(rel_path.parts) - 1
    return "../" * depth if depth > 0 else ""


def _img_path_to_url(img_path: str, root_rel: str) -> str:
    # images are copied to _site/images/<sha-prefix>/<sha>.<ext>
    return f"{root_rel}images/{img_path}"


def _markdown_with_badges(text: str) -> str:
    # Convert [VERIFY] / [MISSING] markers to styled spans BEFORE
    # markdown processing, using HTML so markdown leaves them alone.
    text = VERIFY_RE.sub('<span class="verify">[VERIFY]</span>', text)
    text = MISSING_RE.sub('<span class="missing">[MISSING]</span>', text)
    return md_lib.markdown(text, extensions=["extra", "sane_lists"])


def _photos_with_existence(photos: list, images_root: Path) -> list[dict]:
    out = []
    for p in photos or []:
        if not isinstance(p, dict):
            continue
        ip = p.get("path")
        if not ip:
            continue
        exists = (images_root / ip).exists()
        out.append({**p, "image_exists": exists})
    return out


def render_entry(
    entry: WikiEntry,
    *,
    env: Environment,
    images_root: Path,
    site_root: Path,
    other_entries_by_rel: dict[Path, WikiEntry],
) -> tuple[Path, str]:
    """Render a single WikiEntry to (output_path, html_text)."""
    root_rel = _depth_to_root(entry.rel_path)
    out_rel = entry.rel_path.with_suffix("").parent / "index.html"  # foo/bar/clone-a/index.md -> foo/bar/clone-a/index.html
    out_path = site_root / out_rel
    fm = entry.frontmatter

    # Breadcrumbs
    crumbs = [("Home", root_rel + "index.html")]
    parts = list(entry.rel_path.parts[:-1])  # drop "index.md"
    for i, part in enumerate(parts):
        # Build href back to that ancestor index
        depth_from_here = len(parts) - i - 1
        href = "../" * depth_from_here + "index.html"
        crumbs.append((part, href))

    # Photos: existence-tag and prep
    photos = _photos_with_existence(fm.get("photos", []), images_root)

    title = fm.get("full_name") or fm.get("group_name") or entry.rel_path.parts[-2]

    if entry.type == "cultivar_group":
        # Find member clones in this directory
        members = []
        my_dir = entry.rel_path.parent
        for other in other_entries_by_rel.values():
            other_parent = other.rel_path.parent
            # other is a child if its parent's parent equals my_dir
            if other_parent.parent == my_dir and other.type == "clone":
                child_dirname = other_parent.name
                members.append({
                    "name": other.frontmatter.get("short_name") or other.frontmatter.get("full_name") or child_dirname,
                    "href": f"{child_dirname}/index.html",
                    "reviewed": other.review.get("human_reviewed", False),
                })
        body_html = env.from_string(GROUP_PAGE).render(
            frontmatter=fm,
            review=entry.review,
            short_name=fm.get("group_name") or entry.rel_path.parts[-2],
            body_html=_markdown_with_badges(entry.body_md),
            member_clones=sorted(members, key=lambda m: m["name"]),
        )
    else:
        body_html = env.from_string(CLONE_PAGE).render(
            frontmatter=fm,
            review=entry.review,
            short_name=fm.get("short_name") or fm.get("full_name") or entry.rel_path.parts[-2],
            body_html=_markdown_with_badges(entry.body_md),
            photos=photos,
            open_questions=entry.open_questions,
            image_url=lambda p: _img_path_to_url(p, root_rel),
        )

    page = env.from_string(LAYOUT).render(
        title=title,
        root_rel=root_rel,
        breadcrumbs=crumbs,
        content=body_html,
        generated_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return out_path, page


def render_species_index(
    *,
    env: Environment,
    site_root: Path,
    genus: str,
    species: str,
    species_dir_rel: Path,
    entries: list[WikiEntry],
) -> tuple[Path, str]:
    rows = []
    for e in entries:
        fm = e.frontmatter
        # Direct child directory of species/<species>/ — link is "<dirname>/index.html"
        child = e.rel_path.relative_to(species_dir_rel).parts[0]
        # If entry is a deeper grandchild, still link to it but show its own dir name
        dirname = e.rel_path.parent.relative_to(species_dir_rel).as_posix()
        href = f"{dirname}/index.html"
        loc = ""
        ol = fm.get("origin_locality") or {}
        if isinstance(ol, dict):
            if ol.get("county") and ol.get("state"):
                loc = f"{ol['county']} Co, {ol['state']}"
            elif ol.get("state"):
                loc = ol["state"]
        rows.append({
            "name": fm.get("short_name") or fm.get("full_name") or fm.get("group_name") or child,
            "href": href,
            "locality": loc,
            "year": fm.get("year_first_described_on_forum"),
            "reviewed": (e.review or {}).get("human_reviewed", False),
        })
    rows.sort(key=lambda r: r["name"].lower())

    out_rel = species_dir_rel / "index.html"
    root_rel = _depth_to_root(species_dir_rel / "x")  # +1 segment for the index.html itself doesn't matter

    body = env.from_string(SPECIES_INDEX).render(genus=genus, species=species, entries=rows)
    crumbs = [
        ("Home", root_rel + "index.html"),
        (genus, "../index.html"),
        (species, "index.html"),
    ]
    page = env.from_string(LAYOUT).render(
        title=f"{genus} {species}",
        root_rel=root_rel,
        breadcrumbs=crumbs,
        content=body,
        generated_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return site_root / out_rel, page


def render_genus_index(
    *,
    env: Environment,
    site_root: Path,
    genus: str,
    species_summaries: list[dict],
) -> tuple[Path, str]:
    rows = []
    for s in species_summaries:
        rows.append({
            "name": s["species"],
            "href": f"{s['species']}/index.html",
            "count": s["count"],
        })
    rows.sort(key=lambda r: r["name"])
    body = env.from_string(GENUS_INDEX).render(genus=genus, species_list=rows)
    root_rel = "../"
    crumbs = [
        ("Home", root_rel + "index.html"),
        (genus, "index.html"),
    ]
    page = env.from_string(LAYOUT).render(
        title=genus,
        root_rel=root_rel,
        breadcrumbs=crumbs,
        content=body,
        generated_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return site_root / genus / "index.html", page


def render_root_index(
    *,
    env: Environment,
    site_root: Path,
    genus_summaries: list[dict],
    stats: dict,
) -> tuple[Path, str]:
    rows = []
    for g in genus_summaries:
        rows.append({
            "name": g["genus"],
            "href": f"{g['genus']}/index.html",
            "species_count": g["species_count"],
            "clone_count": g["clone_count"],
        })
    rows.sort(key=lambda r: r["name"])
    body = env.from_string(ROOT_INDEX).render(genera=rows, stats=stats)
    page = env.from_string(LAYOUT).render(
        title="Home",
        root_rel="",
        breadcrumbs=[],
        content=body,
        generated_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return site_root / "index.html", page


# ----------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------


@dataclass
class BuildSummary:
    pages_written: int = 0
    images_linked: int = 0
    skipped: list[str] = field(default_factory=list)


def build_site(
    *,
    wiki_root: Path,
    images_root: Path,
    site_root: Path,
    copy_images: bool = True,
) -> BuildSummary:
    site_root.mkdir(parents=True, exist_ok=True)
    static_dir = site_root / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "style.css").write_text(CSS, encoding="utf-8")

    env = Environment(
        loader=BaseLoader(),
        autoescape=select_autoescape(["html"]),
    )

    entries = load_wiki_entries(wiki_root)
    by_rel = {e.rel_path: e for e in entries}
    summary = BuildSummary()

    # Per-entry pages
    referenced_images: set[str] = set()
    for e in entries:
        out_path, html_text = render_entry(
            e,
            env=env,
            images_root=images_root,
            site_root=site_root,
            other_entries_by_rel=by_rel,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_text, encoding="utf-8")
        summary.pages_written += 1
        for p in (e.frontmatter.get("photos") or []):
            if isinstance(p, dict) and p.get("path"):
                referenced_images.add(p["path"])

    # Per-species and per-genus and root indexes
    # Index entries by genus/species directory
    genus_buckets: dict[str, dict[str, list[WikiEntry]]] = {}
    for e in entries:
        parts = e.rel_path.parts
        if len(parts) < 2:
            continue
        genus = parts[0]
        species = parts[1] if len(parts) > 2 else None
        if species is None:
            continue
        genus_buckets.setdefault(genus, {}).setdefault(species, []).append(e)

    genus_summaries = []
    for genus, species_map in genus_buckets.items():
        species_summaries = []
        for species, ents in species_map.items():
            # Render species index (only counts non-cultivar-group entries as clones)
            clone_entries = [e for e in ents if e.type == "clone"]
            # But list ALL entries on the species page (groups + clones together)
            species_dir_rel = Path(genus) / species
            out_path, html_text = render_species_index(
                env=env,
                site_root=site_root,
                genus=genus,
                species=species,
                species_dir_rel=species_dir_rel,
                entries=ents,
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(html_text, encoding="utf-8")
            summary.pages_written += 1
            species_summaries.append({"species": species, "count": len(clone_entries)})
        # Genus index
        out_path, html_text = render_genus_index(
            env=env,
            site_root=site_root,
            genus=genus,
            species_summaries=species_summaries,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_text, encoding="utf-8")
        summary.pages_written += 1
        clone_total = sum(s["count"] for s in species_summaries)
        genus_summaries.append({"genus": genus, "species_count": len(species_summaries), "clone_count": clone_total})

    # Root index
    stats = {
        "clones": sum(g["clone_count"] for g in genus_summaries),
        "species": sum(g["species_count"] for g in genus_summaries),
        "genera": len(genus_summaries),
    }
    out_path, html_text = render_root_index(
        env=env,
        site_root=site_root,
        genus_summaries=genus_summaries,
        stats=stats,
    )
    out_path.write_text(html_text, encoding="utf-8")
    summary.pages_written += 1

    # Images: only copy ones that are actually referenced (saves disk)
    if copy_images:
        site_images = site_root / "images"
        for ip in sorted(referenced_images):
            src = images_root / ip
            if not src.exists():
                continue
            dst = site_images / ip
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, dst)
            summary.images_linked += 1

    return summary
