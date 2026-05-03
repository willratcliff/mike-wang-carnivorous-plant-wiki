"""Stage 3: mirror referenced images into the local archive.

Walks parsed thread JSON files, downloads every image_url it finds, and
maintains a manifest mapping original URL -> local relative path. Images
are content-addressed (SHA-256) so duplicates across threads share one
file on disk.

Politeness defaults are gentler than the HTML fetcher (Flickr is
unrelated to proboards and has its own rate limits). Failures on
individual images are recorded in the manifest as "failed" but do not
abort the run, since dead Photobucket links are expected.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import mimetypes
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

LOG = logging.getLogger("sarrwiki.image_mirror")

DEFAULT_USER_AGENT = (
    "Sarracenia-Wiki-Archive/0.1 "
    "(image mirror; by request of Mike Wang; contact: wcratcliff@gmail.com)"
)
DEFAULT_RATE_LIMIT_SECONDS = 1.5
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 5.0


@dataclass
class ImageMirrorEntry:
    url: str
    local_path: Optional[str]  # relative to images_root; None if failed
    sha256: Optional[str]
    bytes: Optional[int]
    content_type: Optional[str]
    status: str  # "ok" | "failed" | "skipped"
    error: Optional[str] = None
    fetched_at_iso: Optional[str] = None


@dataclass
class ImageMirror:
    images_root: Path
    manifest_path: Path = field(init=False)
    user_agent: str = DEFAULT_USER_AGENT
    rate_limit_seconds: float = DEFAULT_RATE_LIMIT_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS

    _manifest: dict[str, dict] = field(default_factory=dict, init=False)
    _last_request_at: float = field(default=0.0, init=False)
    _session: requests.Session = field(default_factory=requests.Session, init=False)

    def __post_init__(self) -> None:
        self.images_root = Path(self.images_root)
        self.images_root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.images_root / "manifest.json"
        self._session.headers.update({"User-Agent": self.user_agent})
        self._load_manifest()

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _load_manifest(self) -> None:
        if self.manifest_path.exists():
            try:
                self._manifest = json.loads(self.manifest_path.read_text())
            except json.JSONDecodeError:
                LOG.warning("manifest.json is corrupt — starting fresh")
                self._manifest = {}
        else:
            self._manifest = {}

    def _save_manifest(self) -> None:
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._manifest, indent=2, ensure_ascii=False))
        tmp.replace(self.manifest_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mirror_urls(self, urls: list[str], *, retry_failed: bool = False) -> dict[str, ImageMirrorEntry]:
        """Download a batch of image URLs.

        Returns a dict keyed by URL with an ImageMirrorEntry for each.
        Updates and persists the manifest as it goes (one save per
        successful download + one save at the end).
        """
        results: dict[str, ImageMirrorEntry] = {}
        for url in urls:
            existing = self._manifest.get(url)
            if existing and existing.get("status") == "ok" and not retry_failed:
                results[url] = ImageMirrorEntry(
                    url=url,
                    local_path=existing.get("local_path"),
                    sha256=existing.get("sha256"),
                    bytes=existing.get("bytes"),
                    content_type=existing.get("content_type"),
                    status="skipped",
                    fetched_at_iso=existing.get("fetched_at_iso"),
                )
                continue
            if existing and existing.get("status") == "failed" and not retry_failed:
                results[url] = ImageMirrorEntry(
                    url=url,
                    local_path=None,
                    sha256=None,
                    bytes=None,
                    content_type=None,
                    status="skipped",
                    error=existing.get("error"),
                    fetched_at_iso=existing.get("fetched_at_iso"),
                )
                continue

            entry = self._download_one(url)
            results[url] = entry
            self._manifest[url] = {
                "local_path": entry.local_path,
                "sha256": entry.sha256,
                "bytes": entry.bytes,
                "content_type": entry.content_type,
                "status": entry.status,
                "error": entry.error,
                "fetched_at_iso": entry.fetched_at_iso,
            }
            if entry.status == "ok":
                # Save incrementally so we don't lose progress on a long run.
                self._save_manifest()

        self._save_manifest()
        return results

    def mirror_thread_json(self, thread_json_path: Path) -> dict[str, ImageMirrorEntry]:
        """Convenience: read a parsed thread JSON, mirror all image URLs."""
        data = json.loads(Path(thread_json_path).read_text())
        urls: list[str] = []
        for post in data.get("posts", []):
            urls.extend(post.get("image_urls", []))
        return self.mirror_urls(urls)

    # ------------------------------------------------------------------
    # Download primitive
    # ------------------------------------------------------------------

    def _download_one(self, url: str) -> ImageMirrorEntry:
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            self._wait_for_rate_limit()
            try:
                LOG.info("GET %s (attempt %d/%d)", url, attempt, self.max_retries)
                resp = self._session.get(url, timeout=self.timeout_seconds, stream=False)
                self._last_request_at = time.monotonic()
            except requests.RequestException as exc:
                last_err = f"network: {exc}"
                LOG.warning("network error on %s: %s", url, exc)
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 200:
                content = resp.content
                if not content:
                    last_err = "empty response body"
                    LOG.warning("empty body for %s", url)
                    self._sleep_backoff(attempt)
                    continue

                sha = hashlib.sha256(content).hexdigest()
                content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
                ext = self._extension_for(url, content_type)
                rel_path = f"{sha[:2]}/{sha}{ext}"
                abs_path = self.images_root / rel_path
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                if not abs_path.exists():
                    abs_path.write_bytes(content)
                LOG.info("wrote %s (%d bytes)", rel_path, len(content))
                return ImageMirrorEntry(
                    url=url,
                    local_path=rel_path,
                    sha256=sha,
                    bytes=len(content),
                    content_type=content_type or None,
                    status="ok",
                    fetched_at_iso=dt.datetime.now(dt.timezone.utc).isoformat(),
                )

            if resp.status_code in (404, 410, 403):
                # Dead link — record it and stop retrying.
                LOG.warning("HTTP %d for %s (treating as permanent)", resp.status_code, url)
                return ImageMirrorEntry(
                    url=url,
                    local_path=None,
                    sha256=None,
                    bytes=None,
                    content_type=None,
                    status="failed",
                    error=f"HTTP {resp.status_code}",
                    fetched_at_iso=dt.datetime.now(dt.timezone.utc).isoformat(),
                )

            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                last_err = f"HTTP {resp.status_code}"
                self._sleep_backoff(attempt, retry_after=resp.headers.get("Retry-After"))
                continue

            last_err = f"unexpected HTTP {resp.status_code}"
            return ImageMirrorEntry(
                url=url,
                local_path=None,
                sha256=None,
                bytes=None,
                content_type=None,
                status="failed",
                error=last_err,
                fetched_at_iso=dt.datetime.now(dt.timezone.utc).isoformat(),
            )

        return ImageMirrorEntry(
            url=url,
            local_path=None,
            sha256=None,
            bytes=None,
            content_type=None,
            status="failed",
            error=last_err or "exhausted retries",
            fetched_at_iso=dt.datetime.now(dt.timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wait_for_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.rate_limit_seconds - elapsed
        if wait > 0:
            time.sleep(wait)

    def _sleep_backoff(self, attempt: int, retry_after: Optional[str] = None) -> None:
        if retry_after:
            try:
                time.sleep(float(retry_after))
                return
            except ValueError:
                pass
        time.sleep(self.backoff_base_seconds * (2 ** (attempt - 1)))

    @staticmethod
    def _extension_for(url: str, content_type: str) -> str:
        # Prefer extension from URL path if it looks like a real image extension.
        path = urlparse(url).path
        url_ext = os.path.splitext(path)[1].lower()
        if url_ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}:
            return url_ext
        # Fall back to mimetype-derived ext.
        if content_type:
            guessed = mimetypes.guess_extension(content_type)
            if guessed:
                return guessed
        return ""
