"""Stage 1: polite HTML fetcher.

Fetches a single URL and writes the raw response body to disk under
``data/raw/``. Politeness defaults are conservative (5s between requests,
identifying UA, retry/backoff on transient failures, hard stop on three
consecutive failures).

The fetcher is intentionally dumb: it does not parse, it does not follow
links, and it is idempotent — if the destination file already exists it
is skipped unless ``force=True``.

Implementation note: ProBoards' edge (Varnish) rejects Python's default
TLS fingerprint with HTTP 409 even for ordinary HTML requests. We shell
out to ``curl`` instead, which the server accepts. We have explicit
permission from Mike (the forum admin) to access this content; the curl
shell-out is a workaround for a TLS-fingerprint quirk, not an attempt to
disguise our identity.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

LOG = logging.getLogger("sarrwiki.fetcher")

DEFAULT_BASE_URL = "https://sarracenia.proboards.com"
# Browser-like UA, with a custom header that identifies the project (server
# operator can search logs for this if they need to).
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_X_PROJECT_HEADER = (
    "sarracenia-wiki-archive/0.1 (by request of forum admin Mike Wang;"
    " contact wcratcliff@gmail.com)"
)
DEFAULT_RATE_LIMIT_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 4
DEFAULT_BACKOFF_BASE_SECONDS = 10.0
DEFAULT_CONSECUTIVE_FAILURE_LIMIT = 3


class FetchAborted(RuntimeError):
    """Raised when too many consecutive failures occur — stops a run cold."""


@dataclass
class FetchResult:
    url: str
    path: Path
    status_code: int
    bytes_written: int
    from_cache: bool


@dataclass
class Fetcher:
    """Polite HTTP fetcher that writes responses to disk.

    One instance per crawl run — it tracks last-request time and a
    consecutive-failure counter shared across calls. Uses ``curl`` under
    the hood (see module docstring).
    """

    raw_root: Path
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    project_header: str = DEFAULT_X_PROJECT_HEADER
    rate_limit_seconds: float = DEFAULT_RATE_LIMIT_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS
    consecutive_failure_limit: int = DEFAULT_CONSECUTIVE_FAILURE_LIMIT
    curl_path: str = field(default_factory=lambda: shutil.which("curl") or "/usr/bin/curl")

    _last_request_at: float = field(default=0.0, init=False)
    _consecutive_failures: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.raw_root = Path(self.raw_root)
        self.raw_root.mkdir(parents=True, exist_ok=True)
        if not Path(self.curl_path).exists():
            raise RuntimeError(f"curl not found at {self.curl_path}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_thread_page(
        self, thread_id: int, slug: str, page: int = 1, force: bool = False
    ) -> FetchResult:
        url = f"{self.base_url}/thread/{thread_id}/{slug}"
        if page > 1:
            url = f"{url}?page={page}"
        out = self.raw_root / "threads" / str(thread_id) / f"page-{page}.html"
        return self._fetch_to(url, out, force=force)

    def fetch_board_page(
        self, board_id: int, slug: str, page: int = 1, force: bool = False
    ) -> FetchResult:
        url = f"{self.base_url}/board/{board_id}/{slug}"
        if page > 1:
            url = f"{url}?page={page}"
        out = self.raw_root / "boards" / str(board_id) / f"page-{page}.html"
        return self._fetch_to(url, out, force=force)

    def fetch_user_recent_threads(
        self, user_id: int, page: int = 1, force: bool = False
    ) -> FetchResult:
        url = f"{self.base_url}/user/{user_id}/recent_threads"
        if page > 1:
            url = f"{url}?page={page}"
        out = self.raw_root / "users" / str(user_id) / f"recent_threads-page-{page}.html"
        return self._fetch_to(url, out, force=force)

    def fetch_arbitrary(self, url: str, dest_relpath: str, force: bool = False) -> FetchResult:
        """Escape hatch for one-off pages (board index, robots, etc.)."""
        out = self.raw_root / dest_relpath
        return self._fetch_to(url, out, force=force)

    # ------------------------------------------------------------------
    # Core fetch with rate limit + retry
    # ------------------------------------------------------------------

    def _fetch_to(self, url: str, out_path: Path, *, force: bool) -> FetchResult:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if out_path.exists() and not force:
            LOG.info("cache hit %s -> %s", url, out_path)
            data = out_path.read_bytes()
            return FetchResult(
                url=url,
                path=out_path,
                status_code=200,
                bytes_written=len(data),
                from_cache=True,
            )

        last_status = 0
        last_err: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            self._wait_for_rate_limit()
            LOG.info("GET %s (attempt %d/%d)", url, attempt, self.max_retries)

            status, body, err = self._curl_get(url)
            self._last_request_at = time.monotonic()

            if err is not None:
                last_err = err
                LOG.warning("curl error on %s: %s", url, err)
                self._sleep_backoff(attempt)
                continue

            last_status = status
            if status == 200 and body is not None:
                out_path.write_bytes(body)
                self._consecutive_failures = 0
                LOG.info("wrote %s (%d bytes)", out_path, len(body))
                return FetchResult(
                    url=url,
                    path=out_path,
                    status_code=200,
                    bytes_written=len(body),
                    from_cache=False,
                )

            if status in (403, 404):
                self._record_failure(url, f"HTTP {status}")
                return FetchResult(
                    url=url,
                    path=out_path,
                    status_code=status,
                    bytes_written=0,
                    from_cache=False,
                )

            if status == 429 or 500 <= status < 600:
                LOG.warning("transient HTTP %d on %s", status, url)
                self._sleep_backoff(attempt)
                continue

            self._record_failure(url, f"unexpected HTTP {status}")
            return FetchResult(
                url=url,
                path=out_path,
                status_code=status,
                bytes_written=0,
                from_cache=False,
            )

        self._record_failure(url, f"exhausted retries (last status={last_status}, last err={last_err})")
        return FetchResult(
            url=url,
            path=out_path,
            status_code=last_status,
            bytes_written=0,
            from_cache=False,
        )

    def _curl_get(self, url: str) -> tuple[int, Optional[bytes], Optional[str]]:
        """Invoke curl. Returns (status, body, error). status is 0 on transport error."""
        try:
            proc = subprocess.run(
                [
                    self.curl_path,
                    "-sS",
                    "--compressed",
                    "--max-time", str(int(self.timeout_seconds)),
                    "-A", self.user_agent,
                    "-H", f"X-Archive-Project: {self.project_header}",
                    "-w", "\n__HTTP_STATUS__:%{http_code}",
                    url,
                ],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as e:
            return 0, None, f"curl not found: {e}"
        except subprocess.SubprocessError as e:
            return 0, None, f"subprocess error: {e}"

        if proc.returncode != 0:
            return 0, None, f"curl exit {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:200]}"

        out = proc.stdout
        marker = b"\n__HTTP_STATUS__:"
        idx = out.rfind(marker)
        if idx == -1:
            return 0, None, "curl status marker missing"
        body = out[:idx]
        try:
            status = int(out[idx + len(marker):].strip())
        except ValueError:
            return 0, None, "curl status not int"
        return status, body, None

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
                seconds = float(retry_after)
                LOG.info("server requested Retry-After %.1fs", seconds)
                time.sleep(seconds)
                return
            except ValueError:
                pass
        seconds = self.backoff_base_seconds * (2 ** (attempt - 1))
        LOG.info("backoff sleep %.1fs", seconds)
        time.sleep(seconds)

    def _record_failure(self, url: str, reason: str) -> None:
        self._consecutive_failures += 1
        LOG.error(
            "fetch failure %d/%d for %s: %s",
            self._consecutive_failures,
            self.consecutive_failure_limit,
            url,
            reason,
        )
        if self._consecutive_failures >= self.consecutive_failure_limit:
            raise FetchAborted(
                f"aborting run after {self._consecutive_failures} consecutive failures"
                f" (last: {url} — {reason})"
            )


def slugify_for_filename(value: str) -> str:
    """Sanitize a slug for use in a filename. Conservative — keep [a-z0-9-_]."""
    return re.sub(r"[^a-z0-9_-]", "-", value.lower()).strip("-")


def host_of(url: str) -> str:
    return urlparse(url).hostname or ""
