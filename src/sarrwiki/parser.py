"""Stage 2: parse a saved thread/board HTML page into structured JSON.

Pure function over already-fetched HTML. Does not touch the network.

Designed to fail loudly when the markup looks unfamiliar — better to
notice a parser miss than to silently produce empty fields.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

LOG = logging.getLogger("sarrwiki.parser")

PROBOARDS_BASE = "https://sarracenia.proboards.com"

# A regex that matches /thread/<id>/<slug> URLs (with optional ?page=N).
THREAD_URL_RE = re.compile(r"/thread/(?P<id>\d+)/(?P<slug>[a-z0-9-]+)(?:\?page=(?P<page>\d+))?")
BOARD_URL_RE = re.compile(r"/board/(?P<id>\d+)/(?P<slug>[a-z0-9-]+)(?:\?page=(?P<page>\d+))?")

IMG_HOST_PATTERNS = (
    "staticflickr.com",
    "flickr.com",
    "photobucket.com",
    "imgur.com",
    "i.imgur.com",
    "storage.googleapis.com",
)


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------


@dataclass
class ParsedPost:
    post_id: int
    author_username: Optional[str]
    author_user_id: Optional[int]
    timestamp_iso: Optional[str]
    timestamp_epoch_ms: Optional[int]
    timestamp_raw: Optional[str]
    body_html: str
    body_text: str
    image_urls: list[str] = field(default_factory=list)
    quoted_post_ids: list[int] = field(default_factory=list)


@dataclass
class ParsedThreadPage:
    thread_id: int
    thread_slug: str
    thread_title: Optional[str]
    board_id: Optional[int]
    board_slug: Optional[str]
    board_title: Optional[str]
    breadcrumb: list[str]
    page: int
    total_pages: int
    posts: list[ParsedPost]
    parser_warnings: list[str] = field(default_factory=list)
    source_url: Optional[str] = None
    parsed_at_iso: str = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )


@dataclass
class BoardThreadEntry:
    thread_id: int
    thread_slug: str
    title: str
    starter_username: Optional[str]
    starter_user_id: Optional[int]
    reply_count: Optional[int]
    view_count: Optional[int]
    last_post_epoch_ms: Optional[int]


@dataclass
class ParsedBoardPage:
    board_id: int
    board_slug: str
    board_title: Optional[str]
    page: int
    total_pages: int
    threads: list[BoardThreadEntry]
    parser_warnings: list[str] = field(default_factory=list)
    source_url: Optional[str] = None
    parsed_at_iso: str = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _int_or_none(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _epoch_ms_to_iso(epoch_ms: Optional[int]) -> Optional[str]:
    if epoch_ms is None:
        return None
    return dt.datetime.fromtimestamp(epoch_ms / 1000.0, tz=dt.timezone.utc).isoformat()


SKIP_IMAGE_URL_PATTERNS = (
    # ProBoards forum smileys / emoticons / interface chrome
    "storage.proboards.com/forum/images/smiley/",
    "storage.proboards.com/forum/images/emoticons/",
    "storage.proboards.com/v5/images/",
    "storage.proboards.com/forum/skins/",
)


def _should_skip_image_url(url: str) -> bool:
    return any(p in url for p in SKIP_IMAGE_URL_PATTERNS)


def _extract_image_urls(message: Tag) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for img in message.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        absolute = urljoin(PROBOARDS_BASE, src)
        if _should_skip_image_url(absolute):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        urls.append(absolute)
    return urls


def _is_external_image_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return any(host.endswith(p) for p in IMG_HOST_PATTERNS)


def _detect_pagination(soup: BeautifulSoup, slug: str) -> int:
    """Return the highest page number referenced for this thread/board slug.

    Returns 1 if no pagination is found.
    """
    text_blob = str(soup)
    pattern = re.compile(rf"/(?:thread|board)/\d+/{re.escape(slug)}\?page=(\d+)")
    pages = [int(m) for m in pattern.findall(text_blob)]
    if not pages:
        return 1
    return max(pages)


def _extract_breadcrumb(soup: BeautifulSoup) -> list[str]:
    nav = soup.find(class_="nav-tree-wrapper")
    if not nav:
        return []
    items = []
    for li in nav.find_all("li", class_=lambda c: c and "nav-tree-branch" in c):
        text = li.get_text(strip=True)
        if text:
            items.append(text)
    return items


def _extract_board_from_breadcrumb(soup: BeautifulSoup) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """Return (board_id, board_slug, board_title) from the active breadcrumb.

    The active breadcrumb path is the chain of <li> elements inside
    nav-tree-wrapper, *not* the broader sitemap that ProBoards also
    renders. The last branch before the thread title is the immediate
    board.
    """
    nav = soup.find(class_="nav-tree-wrapper")
    if not nav:
        return None, None, None

    branches = nav.find_all("li", class_=lambda c: c and "nav-tree-branch" in c, recursive=True)
    # The breadcrumb chain typically: Forum > [board chain ...] > Thread title
    # The thread title is the last branch and has no link.
    # Walk backwards and pick the first one with a /board/<id>/<slug> link.
    for li in reversed(branches):
        a = li.find("a", href=True)
        if a:
            m = re.match(r"^/board/(\d+)/([a-z0-9-]+)", a["href"])
            if m:
                return int(m.group(1)), m.group(2), li.get_text(strip=True)
    return None, None, None


# ----------------------------------------------------------------------
# Thread page parsing
# ----------------------------------------------------------------------


def parse_thread_page(
    html: str,
    *,
    thread_id: int,
    thread_slug: str,
    page: int,
    source_url: Optional[str] = None,
) -> ParsedThreadPage:
    soup = BeautifulSoup(html, "lxml")
    warnings: list[str] = []

    # Title — prefer h1, fall back to <title>
    h1 = soup.find("h1")
    if h1:
        thread_title = h1.get_text(strip=True)
    else:
        title_tag = soup.find("title")
        thread_title = title_tag.get_text(strip=True) if title_tag else None
        if thread_title:
            warnings.append("title taken from <title> not <h1>")

    board_id, board_slug, board_title = _extract_board_from_breadcrumb(soup)
    if board_id is None:
        warnings.append("could not extract board from breadcrumb")

    breadcrumb = _extract_breadcrumb(soup)
    total_pages = _detect_pagination(soup, thread_slug)

    posts: list[ParsedPost] = []
    # Match only `post-<digits>` exactly (not `post-<digits>-options` etc).
    post_id_re = re.compile(r"^post-(\d+)$")
    post_nodes = soup.find_all(id=lambda x: bool(x and post_id_re.match(x)))
    if not post_nodes:
        warnings.append("no post nodes found — markup may have changed")

    for node in post_nodes:
        post_id_str = node.get("id", "").removeprefix("post-")
        post_id = _int_or_none(post_id_str)
        if post_id is None:
            warnings.append(f"could not parse post id from {node.get('id')!r}")
            continue

        # Author — first o-user-link inside the post
        user_link = node.find(class_="o-user-link")
        author_username = None
        author_user_id = None
        if user_link:
            title = user_link.get("title", "")
            if title.startswith("@"):
                author_username = title.removeprefix("@")
            author_user_id = _int_or_none(user_link.get("data-id"))
        else:
            # Deleted forum users have a mini-profile of class
            # "deleted-mini-profile" with no user link. The post body
            # itself is preserved.
            if node.find(class_="deleted-mini-profile") or node.find(class_="user-deleted"):
                author_username = "[deleted user]"
            elif node.find(class_="guest-mini-profile") or node.find(class_="user-guest"):
                # Guest posts: not-logged-in users. Their display name
                # lives in span.user-guest.
                guest_name = node.find(class_="user-guest")
                if guest_name:
                    author_username = f"[guest] {guest_name.get_text(strip=True)}"
                else:
                    author_username = "[guest]"
            else:
                warnings.append(f"post {post_id}: no o-user-link found")

        # Timestamp — first abbr.o-timestamp inside the post
        timestamp_epoch_ms = None
        timestamp_raw = None
        ts_abbr = node.find("abbr", class_="o-timestamp")
        if ts_abbr:
            timestamp_epoch_ms = _int_or_none(ts_abbr.get("data-timestamp"))
            timestamp_raw = ts_abbr.get("title") or ts_abbr.get_text(strip=True)
        else:
            warnings.append(f"post {post_id}: no o-timestamp abbr found")

        # Body — div.message inside the post
        message = node.find(class_="message")
        if message is None:
            warnings.append(f"post {post_id}: no .message body found")
            body_html = ""
            body_text = ""
            image_urls: list[str] = []
        else:
            body_html = message.decode_contents()
            body_text = message.get_text("\n", strip=True)
            image_urls = _extract_image_urls(message)

        # Quoted posts — proboards renders quotes as blockquotes; the
        # author/source link inside often references /post/<id> or has a
        # data-id. Conservative: scan the body for /post/<id> hrefs.
        quoted_post_ids: list[int] = []
        if message is not None:
            for a in message.find_all("a", href=True):
                m = re.search(r"/post/(\d+)", a["href"])
                if m:
                    quoted_post_ids.append(int(m.group(1)))

        posts.append(
            ParsedPost(
                post_id=post_id,
                author_username=author_username,
                author_user_id=author_user_id,
                timestamp_iso=_epoch_ms_to_iso(timestamp_epoch_ms),
                timestamp_epoch_ms=timestamp_epoch_ms,
                timestamp_raw=timestamp_raw,
                body_html=body_html,
                body_text=body_text,
                image_urls=image_urls,
                quoted_post_ids=sorted(set(quoted_post_ids)),
            )
        )

    return ParsedThreadPage(
        thread_id=thread_id,
        thread_slug=thread_slug,
        thread_title=thread_title,
        board_id=board_id,
        board_slug=board_slug,
        board_title=board_title,
        breadcrumb=breadcrumb,
        page=page,
        total_pages=total_pages,
        posts=posts,
        parser_warnings=warnings,
        source_url=source_url,
    )


# ----------------------------------------------------------------------
# Board page (thread index) parsing
# ----------------------------------------------------------------------


def parse_board_page(
    html: str,
    *,
    board_id: int,
    board_slug: str,
    page: int,
    source_url: Optional[str] = None,
) -> ParsedBoardPage:
    soup = BeautifulSoup(html, "lxml")
    warnings: list[str] = []

    h1 = soup.find("h1")
    board_title = h1.get_text(strip=True) if h1 else None

    total_pages = _detect_pagination(soup, board_slug)

    threads: list[BoardThreadEntry] = []
    # ProBoards thread rows have ids like "thread-NNNN" (singular) or are
    # within a list. Be defensive — find any anchor pointing to a thread.
    seen_ids: set[int] = set()
    for a in soup.find_all("a", href=True):
        m = THREAD_URL_RE.search(a["href"])
        if not m:
            continue
        tid = int(m.group("id"))
        if tid in seen_ids:
            continue
        seen_ids.add(tid)

        slug = m.group("slug")
        # Walk up to find the row context for metadata.
        row = a.find_parent(["tr", "li", "div"])
        starter_username = None
        starter_user_id = None
        reply_count = None
        view_count = None
        last_post_epoch_ms = None

        if row:
            user_link = row.find(class_="o-user-link")
            if user_link:
                title = user_link.get("title", "")
                if title.startswith("@"):
                    starter_username = title.removeprefix("@")
                starter_user_id = _int_or_none(user_link.get("data-id"))
            ts_abbr = row.find("abbr", class_="o-timestamp")
            if ts_abbr:
                last_post_epoch_ms = _int_or_none(ts_abbr.get("data-timestamp"))

        threads.append(
            BoardThreadEntry(
                thread_id=tid,
                thread_slug=slug,
                title=a.get_text(strip=True) or slug,
                starter_username=starter_username,
                starter_user_id=starter_user_id,
                reply_count=reply_count,
                view_count=view_count,
                last_post_epoch_ms=last_post_epoch_ms,
            )
        )

    if not threads:
        warnings.append("no thread links found on board page")

    return ParsedBoardPage(
        board_id=board_id,
        board_slug=board_slug,
        board_title=board_title,
        page=page,
        total_pages=total_pages,
        threads=threads,
        parser_warnings=warnings,
        source_url=source_url,
    )


# ----------------------------------------------------------------------
# User recent_threads parsing — list of threads started by a user
# ----------------------------------------------------------------------


def parse_user_recent_threads(
    html: str,
    *,
    user_id: int,
    page: int,
    source_url: Optional[str] = None,
) -> dict:
    """Parse a /user/<id>/recent_threads page.

    Returns a plain dict with: user_id, page, total_pages, threads (list
    of {thread_id, slug, title}). We keep it lightweight because this
    page exists primarily to enumerate threads — the canonical metadata
    lives on the threads themselves.
    """
    soup = BeautifulSoup(html, "lxml")

    # The page lists threads via /thread/<id>/<slug> hrefs. Pagination
    # uses /user/<id>/recent_threads?page=N.
    text_blob = str(soup)
    page_pattern = re.compile(rf"/user/{user_id}/recent_threads\?page=(\d+)")
    page_nums = [int(m) for m in page_pattern.findall(text_blob)]
    total_pages = max(page_nums) if page_nums else 1

    seen: dict[int, dict] = {}
    for a in soup.find_all("a", href=True):
        m = THREAD_URL_RE.search(a["href"])
        if not m:
            continue
        tid = int(m.group("id"))
        if tid in seen:
            continue
        # Skip the pagination links — they have ?page= in href but no slug change
        title = a.get_text(strip=True)
        if not title or title.isdigit():
            continue
        seen[tid] = {
            "thread_id": tid,
            "thread_slug": m.group("slug"),
            "title": title,
        }

    return {
        "user_id": user_id,
        "page": page,
        "total_pages": total_pages,
        "threads": list(seen.values()),
        "source_url": source_url,
        "parsed_at_iso": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# ----------------------------------------------------------------------
# Serialization
# ----------------------------------------------------------------------


def thread_page_to_json(parsed: ParsedThreadPage) -> str:
    return json.dumps(asdict(parsed), indent=2, ensure_ascii=False)


def board_page_to_json(parsed: ParsedBoardPage) -> str:
    return json.dumps(asdict(parsed), indent=2, ensure_ascii=False)


def write_thread_page(parsed: ParsedThreadPage, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(thread_page_to_json(parsed), encoding="utf-8")


def write_board_page(parsed: ParsedBoardPage, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(board_page_to_json(parsed), encoding="utf-8")
