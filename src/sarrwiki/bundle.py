"""Render a parsed thread (potentially multi-page) into a single
readable Markdown document.

This is intentionally mechanical:
- Concatenates all pages of a thread, posts in chronological order.
- Marks Mike's posts ("**Mike Wang (meizzwang)**") distinctly from
  replies ("*<username>*").
- Rewrites image references: if the URL is in the image manifest with
  a local mirror, link to the local path; otherwise leave the original
  URL with a "[broken]" or "[not mirrored]" tag.
- Preserves quoted-reply chains by surfacing referenced post IDs.

No schema decisions. No clone-extraction logic. The output is the
input the synthesis layer (or a human reviewer) will read.
"""

from __future__ import annotations

import datetime as dt
import html as _html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

MIKE_USER_ID = 11
MIKE_USERNAME = "meizzwang"


@dataclass
class BundleSettings:
    parsed_threads_root: Path
    images_manifest_path: Path
    images_root: Path
    out_root: Path
    image_path_prefix: str = "../../images/"  # relative path from bundle to image


def load_image_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_thread_pages(parsed_threads_root: Path, thread_id: int) -> list[dict]:
    """Return all parsed JSON pages for a thread, sorted by page number."""
    tdir = parsed_threads_root / str(thread_id)
    pages = []
    for jf in sorted(tdir.glob("page-*.json")):
        try:
            pages.append(json.loads(jf.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    pages.sort(key=lambda p: p.get("page", 0))
    return pages


def _img_replacement(url: str, manifest: dict, image_path_prefix: str) -> tuple[str, str]:
    """Return (local_or_original_url, status_tag).

    status_tag is "" if mirrored, " [broken]" if known dead, " [not
    mirrored]" if absent from manifest.
    """
    entry = manifest.get(url)
    if entry and entry.get("status") == "ok" and entry.get("local_path"):
        return image_path_prefix + entry["local_path"], ""
    if entry and entry.get("status") == "failed":
        return url, " [broken]"
    return url, " [not mirrored]"


def render_post_body(body_html: str, manifest: dict, image_path_prefix: str) -> str:
    """Convert the proboards post HTML to Markdown-ish text.

    We don't try to be perfect: just preserve paragraphs, line breaks,
    blockquotes, links, and images. Anything else falls through as
    plain text from BeautifulSoup.get_text().
    """
    soup = BeautifulSoup(body_html, "lxml")

    def walk(node, sink: list[str]) -> None:
        if isinstance(node, NavigableString):
            sink.append(str(node))
            return
        if not isinstance(node, Tag):
            return

        name = node.name.lower()
        if name == "br":
            sink.append("  \n")
        elif name in ("p", "div"):
            for c in node.children:
                walk(c, sink)
            sink.append("\n\n")
        elif name == "img":
            src = node.get("src") or node.get("data-src") or ""
            if src:
                local, status = _img_replacement(src, manifest, image_path_prefix)
                alt = node.get("alt") or ""
                sink.append(f"\n\n![{alt}]({local}){status}\n\n")
        elif name == "a":
            href = node.get("href") or ""
            inner = "".join(_text_of(c) for c in node.children).strip()
            if not inner:
                inner = href
            sink.append(f"[{inner}]({href})")
        elif name in ("strong", "b"):
            sink.append("**")
            for c in node.children:
                walk(c, sink)
            sink.append("**")
        elif name in ("em", "i"):
            sink.append("*")
            for c in node.children:
                walk(c, sink)
            sink.append("*")
        elif name == "blockquote":
            inner_parts: list[str] = []
            for c in node.children:
                walk(c, inner_parts)
            inner_text = "".join(inner_parts).strip()
            quoted = inner_text.replace("\n", "\n> ")
            sink.append(f"\n\n> {quoted}\n\n")
        elif name in ("ul", "ol"):
            sink.append("\n")
            for c in node.children:
                walk(c, sink)
            sink.append("\n")
        elif name == "li":
            sink.append("- ")
            for c in node.children:
                walk(c, sink)
            sink.append("\n")
        else:
            for c in node.children:
                walk(c, sink)

    out_parts: list[str] = []
    walk(soup, out_parts)
    text = "".join(out_parts)
    # Decode HTML entities that BeautifulSoup may have left
    text = _html.unescape(text)
    # Normalize excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _text_of(node) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if isinstance(node, Tag):
        return node.get_text()
    return ""


def render_thread_bundle(
    *,
    thread_id: int,
    parsed_threads_root: Path,
    manifest: dict,
    image_path_prefix: str,
) -> Optional[str]:
    pages = collect_thread_pages(parsed_threads_root, thread_id)
    if not pages:
        return None

    first = pages[0]
    title = first.get("thread_title") or first.get("thread_slug") or f"thread {thread_id}"
    board_id = first.get("board_id")
    board_title = first.get("board_title")
    breadcrumb = first.get("breadcrumb") or []
    source_url = first.get("source_url")

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("> **Archive metadata.** This document is a verbatim mirror of "
                 "the source forum thread, regenerated from cached HTML and image "
                 "downloads. It is not yet a curated wiki entry.")
    lines.append("")
    lines.append(f"- **Thread ID:** [{thread_id}]({source_url or ''})")
    if board_id is not None:
        lines.append(f"- **Board:** {board_title or ''} (`/board/{board_id}/`)")
    if breadcrumb:
        lines.append(f"- **Breadcrumb:** {' › '.join(breadcrumb)}")
    lines.append(f"- **Pages archived:** {len(pages)} of {first.get('total_pages', '?')}")
    total_posts = sum(len(p.get("posts", [])) for p in pages)
    lines.append(f"- **Posts archived:** {total_posts}")
    lines.append(f"- **Bundle generated:** {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Flatten all posts, preserve page boundaries as markers
    post_index_global = 0
    for page in pages:
        if len(pages) > 1:
            lines.append(f"### Page {page.get('page', '?')}")
            lines.append("")
        for post in page.get("posts", []):
            post_index_global += 1
            author = post.get("author_username") or "[unknown]"
            user_id = post.get("author_user_id")
            ts_iso = post.get("timestamp_iso") or ""
            ts_raw = post.get("timestamp_raw") or ""
            post_id = post.get("post_id")
            body_html = post.get("body_html") or ""
            quoted = post.get("quoted_post_ids") or []

            if user_id == MIKE_USER_ID:
                byline = f"#### **Mike Wang** (`@{author}`)"
            else:
                byline = f"#### *{author}*"

            lines.append(byline)
            ts_display = ts_iso[:19].replace("T", " ") + " UTC" if ts_iso else ts_raw
            lines.append(f"`post #{post_index_global}` · `id={post_id}` · `{ts_display}`")
            if quoted:
                lines.append(f"*quotes posts: {', '.join(str(q) for q in quoted)}*")
            lines.append("")
            body = render_post_body(body_html, manifest, image_path_prefix)
            lines.append(body)
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def write_bundle(
    *,
    thread_id: int,
    parsed_threads_root: Path,
    manifest: dict,
    out_root: Path,
    image_path_prefix: str,
) -> Optional[Path]:
    md = render_thread_bundle(
        thread_id=thread_id,
        parsed_threads_root=parsed_threads_root,
        manifest=manifest,
        image_path_prefix=image_path_prefix,
    )
    if md is None:
        return None
    out_path = out_root / "threads" / f"{thread_id:06d}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    return out_path
