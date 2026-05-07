"""Probe non-Flickr image URLs to find broken/blocked ones.

Strategy:
- Flickr URLs are trusted (13,753 photos) — skip probing them.
- Photobucket URLs are blanket-marked as broken — PB blocks hotlinks
  from non-PB referrers since 2017.
- Other hosts (postimg, imgur, personal sites, Tapatalk CDN, etc.) get
  a HEAD probe with a short timeout. Anything that 4xx's, times out,
  or errors is marked broken.

For the broken set we:
  1) Copy data/images/<prefix>/<sha>.<ext> to
     web/public/img-fallback/<sha>.<ext>.
  2) Write the list of broken SHAs to web/src/data/broken-shas.json.

The frontend's photos.ts reads that JSON and serves /img-fallback/<sha>.<ext>
instead of the original URL for those SHAs.
"""
from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "images" / "manifest.json"
LOCAL_IMG_ROOT = ROOT / "data" / "images"
FALLBACK_OUT = ROOT / "web" / "public" / "img-fallback"
BROKEN_SHAS_OUT = ROOT / "web" / "src" / "data" / "broken-shas.json"

CONCURRENCY = 30
TIMEOUT = 10  # seconds per request

# Common UA to avoid being filtered by sites that block default Python UAs.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_flickr(host: str) -> bool:
    return "flickr.com" in host or host.startswith("c1.staticflickr") or "staticflickr.com" in host


def is_photobucket(host: str) -> bool:
    return "photobucket.com" in host


def probe(url: str) -> tuple[str, bool, str]:
    """HEAD-probe a URL. Returns (url, alive, reason).
    A site that 4xx's, errors, or redirects to a homepage is considered dead.
    """
    try:
        r = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code >= 400:
            return url, False, f"HTTP {r.status_code}"
        # Some servers do not honor HEAD properly. Fall back to a tiny GET.
        ct = r.headers.get("content-type", "").lower()
        if not ct.startswith("image/"):
            # Try GET with Range header — some hosts strip content-type on HEAD.
            try:
                r2 = requests.get(
                    url,
                    headers={**HEADERS, "Range": "bytes=0-127"},
                    timeout=TIMEOUT,
                    stream=True,
                    allow_redirects=True,
                )
                if r2.status_code >= 400:
                    return url, False, f"GET HTTP {r2.status_code}"
                ct = r2.headers.get("content-type", "").lower()
                # Read only the first chunk and discard.
                _ = next(r2.iter_content(128), b"")
                r2.close()
                if not ct.startswith("image/"):
                    return url, False, f"non-image content-type ({ct or '?'})"
            except requests.RequestException as e:
                return url, False, f"GET err: {type(e).__name__}"
        return url, True, "ok"
    except requests.RequestException as e:
        return url, False, f"err: {type(e).__name__}"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    print(f"manifest entries: {len(manifest)}")

    to_probe: list[str] = []
    blanket_broken: list[str] = []
    flickr_skip = 0
    failed_in_manifest = 0

    for url, meta in manifest.items():
        if meta.get("status") != "ok":
            failed_in_manifest += 1
            continue
        host = host_of(url)
        if is_flickr(host):
            flickr_skip += 1
            continue
        if is_photobucket(host):
            blanket_broken.append(url)
            continue
        to_probe.append(url)

    print(f"  flickr (trusted, skipped):    {flickr_skip}")
    print(f"  photobucket (blanket-broken): {len(blanket_broken)}")
    print(f"  to probe:                     {len(to_probe)}")
    print(f"  manifest already-failed:      {failed_in_manifest}")
    print()

    print(f"probing {len(to_probe)} URLs (concurrency={CONCURRENCY}, timeout={TIMEOUT}s)...")
    broken_urls: list[tuple[str, str]] = [(u, "photobucket-blanket") for u in blanket_broken]
    alive = 0
    done = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(probe, u) for u in to_probe]
        for fut in as_completed(futures):
            url, ok, reason = fut.result()
            done += 1
            if ok:
                alive += 1
            else:
                broken_urls.append((url, reason))
            if done % 200 == 0 or done == len(to_probe):
                print(f"  progress: {done}/{len(to_probe)}  alive={alive}  broken={len(broken_urls) - len(blanket_broken)}")

    probed_broken = len(broken_urls) - len(blanket_broken)
    print()
    print(f"probe done. alive={alive}  broken={probed_broken}  (+ {len(blanket_broken)} pb-blanket = {len(broken_urls)} total broken)")

    # Map broken URLs → SHAs and copy local files.
    print()
    FALLBACK_OUT.mkdir(parents=True, exist_ok=True)
    BROKEN_SHAS_OUT.parent.mkdir(parents=True, exist_ok=True)

    broken_shas: dict[str, str] = {}  # sha → ext
    missing_local = 0
    bytes_copied = 0
    for url, reason in broken_urls:
        meta = manifest.get(url, {})
        sha = meta.get("sha256")
        local_path = meta.get("local_path", "")
        if not sha or not local_path:
            missing_local += 1
            continue
        src = LOCAL_IMG_ROOT / local_path
        if not src.exists():
            missing_local += 1
            continue
        ext = local_path.rsplit(".", 1)[-1] if "." in local_path else "jpg"
        dst = FALLBACK_OUT / f"{sha}.{ext}"
        if not dst.exists():
            shutil.copy2(src, dst)
            bytes_copied += dst.stat().st_size
        broken_shas[sha] = ext

    print(f"copied {len(broken_shas)} fallback images ({bytes_copied/1024/1024:.1f} MB) to {FALLBACK_OUT.relative_to(ROOT)}")
    if missing_local:
        print(f"  ({missing_local} broken URLs had no local copy — silently dropped)")

    BROKEN_SHAS_OUT.write_text(json.dumps(broken_shas, indent=0, separators=(",", ":")))
    print(f"wrote {BROKEN_SHAS_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
