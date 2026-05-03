"""High-level orchestration: fetch -> parse -> image-mirror for a thread.

Exposes a single function ``archive_thread`` that runs all three stages
for one thread (across all its pages), idempotently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .fetcher import Fetcher, FetchResult
from .image_mirror import ImageMirror
from .parser import (
    ParsedThreadPage,
    parse_thread_page,
    write_thread_page,
)

LOG = logging.getLogger("sarrwiki.pipeline")


@dataclass
class ThreadArchiveResult:
    thread_id: int
    thread_slug: str
    pages_fetched: int
    posts_total: int
    images_attempted: int
    images_ok: int
    images_failed: int
    parser_warnings: list[str] = field(default_factory=list)


def archive_thread(
    *,
    thread_id: int,
    thread_slug: str,
    raw_root: Path,
    parsed_root: Path,
    images_root: Path,
    fetcher: Optional[Fetcher] = None,
    image_mirror: Optional[ImageMirror] = None,
    skip_images: bool = False,
    force: bool = False,
) -> ThreadArchiveResult:
    """Fetch every page of a thread, parse each, and mirror images.

    Idempotent: re-runs reuse cached HTML and images unless ``force`` is set.
    """
    raw_root = Path(raw_root)
    parsed_root = Path(parsed_root)
    images_root = Path(images_root)

    fetcher = fetcher or Fetcher(raw_root=raw_root)
    image_mirror = image_mirror or ImageMirror(images_root=images_root)

    parsed_thread_dir = parsed_root / "threads" / str(thread_id)
    parsed_thread_dir.mkdir(parents=True, exist_ok=True)

    # ---- page 1 first to learn total_pages ----
    page = 1
    fetch_result = fetcher.fetch_thread_page(thread_id, thread_slug, page=page, force=force)
    if fetch_result.status_code != 200 and not fetch_result.from_cache:
        LOG.error("could not fetch page 1 of thread %d: HTTP %s", thread_id, fetch_result.status_code)
        return ThreadArchiveResult(
            thread_id=thread_id,
            thread_slug=thread_slug,
            pages_fetched=0,
            posts_total=0,
            images_attempted=0,
            images_ok=0,
            images_failed=0,
        )

    parsed_pages: list[ParsedThreadPage] = []
    parsed = _parse_and_write(fetch_result, thread_id, thread_slug, page, parsed_thread_dir)
    parsed_pages.append(parsed)
    total_pages = parsed.total_pages

    # ---- remaining pages ----
    for page in range(2, total_pages + 1):
        fr = fetcher.fetch_thread_page(thread_id, thread_slug, page=page, force=force)
        if fr.status_code != 200 and not fr.from_cache:
            LOG.warning("page %d of thread %d failed (HTTP %s) — continuing", page, thread_id, fr.status_code)
            continue
        parsed_pages.append(_parse_and_write(fr, thread_id, thread_slug, page, parsed_thread_dir))

    posts_total = sum(len(p.posts) for p in parsed_pages)
    parser_warnings: list[str] = []
    for p in parsed_pages:
        for w in p.parser_warnings:
            parser_warnings.append(f"page {p.page}: {w}")

    # ---- image mirroring ----
    image_urls: list[str] = []
    for p in parsed_pages:
        for post in p.posts:
            image_urls.extend(post.image_urls)
    image_urls = list(dict.fromkeys(image_urls))  # de-dup, preserve order

    images_ok = 0
    images_failed = 0
    if not skip_images and image_urls:
        results = image_mirror.mirror_urls(image_urls)
        for entry in results.values():
            if entry.status == "ok" or (entry.status == "skipped" and entry.local_path):
                images_ok += 1
            elif entry.status == "failed" or (entry.status == "skipped" and entry.error):
                images_failed += 1

    return ThreadArchiveResult(
        thread_id=thread_id,
        thread_slug=thread_slug,
        pages_fetched=len(parsed_pages),
        posts_total=posts_total,
        images_attempted=len(image_urls),
        images_ok=images_ok,
        images_failed=images_failed,
        parser_warnings=parser_warnings,
    )


def _parse_and_write(
    fr: FetchResult,
    thread_id: int,
    thread_slug: str,
    page: int,
    parsed_dir: Path,
) -> ParsedThreadPage:
    html = fr.path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_thread_page(
        html,
        thread_id=thread_id,
        thread_slug=thread_slug,
        page=page,
        source_url=fr.url,
    )
    out = parsed_dir / f"page-{page}.json"
    write_thread_page(parsed, out)
    LOG.info("wrote %s (%d posts)", out, len(parsed.posts))
    return parsed
