"""Build a hash→URL reverse index from data/images/manifest.json.

The manifest is keyed by original URL with `local_path`/`sha256`/`status`
in each value. Wiki frontmatter stores photos by local path
(e.g. "b9/b93f...e21af.jpg"). To render those photos on the website
without self-hosting, we need to look up the original URL from the
hash.

Output: web/src/data/image-urls.json
  { "<sha256>": { "url": "...", "ext": "jpg" }, ... }

Skips manifest entries with status != "ok" — those failed to fetch and
their URLs are likely already dead.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "images" / "manifest.json"
OUT = ROOT / "web" / "src" / "data" / "image-urls.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    print(f"manifest entries: {len(manifest)}")

    by_status: Counter[str] = Counter()
    by_host: Counter[str] = Counter()
    out: dict[str, dict[str, str]] = {}
    duplicates = 0

    for url, meta in manifest.items():
        status = meta.get("status", "unknown")
        by_status[status] += 1
        if status != "ok":
            continue
        sha = meta.get("sha256")
        if not sha:
            continue
        # Track host for visibility into where photos live.
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc.lower()
            by_host[host] += 1
        except Exception:
            host = "?"

        # Extract extension from local_path (more reliable than URL).
        local_path = meta.get("local_path", "")
        ext = local_path.rsplit(".", 1)[-1] if "." in local_path else ""

        if sha in out:
            duplicates += 1
            # Prefer non-photobucket hosts (they hotlink-block).
            if "photobucket" in host and "photobucket" not in out[sha]["url"]:
                continue  # keep existing non-PB URL
        out[sha] = {"url": url, "ext": ext, "host": host}

    print(f"\nstatus counts:")
    for s, n in by_status.most_common():
        print(f"  {s}: {n}")

    print(f"\ntop hosts (status=ok only):")
    for h, n in by_host.most_common(10):
        print(f"  {h}: {n}")

    print(f"\nunique sha256 in output: {len(out)}")
    print(f"duplicate sha256s collapsed: {duplicates}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=0, separators=(",", ":")))
    print(f"\nwrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
