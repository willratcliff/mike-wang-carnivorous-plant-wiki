"""Bulk archive runner: walks every thread in a discovered-threads list
and runs the pipeline on each.

Resumable: progress is tracked in a JSON state file. Re-runs skip
already-completed threads. Ctrl-C is safe — partial state is flushed to
disk after each thread.

Usage:
    .venv/bin/python scripts/archive_user_threads.py 11
    .venv/bin/python scripts/archive_user_threads.py 11 --skip-images
    .venv/bin/python scripts/archive_user_threads.py 11 --limit 10
    .venv/bin/python scripts/archive_user_threads.py 11 --retry-failed
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import signal
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sarrwiki.fetcher import Fetcher, FetchAborted  # noqa: E402
from sarrwiki.image_mirror import ImageMirror  # noqa: E402
from sarrwiki.pipeline import archive_thread  # noqa: E402

LOG = logging.getLogger("archive_user_threads")


@dataclass
class ThreadState:
    thread_id: int
    thread_slug: str
    title: str
    status: str = "pending"  # pending | done | failed
    pages_fetched: int = 0
    posts_total: int = 0
    images_ok: int = 0
    images_failed: int = 0
    images_attempted: int = 0
    parser_warnings: list[str] = field(default_factory=list)
    error: str = ""
    started_at_iso: str = ""
    completed_at_iso: str = ""


@dataclass
class ProgressFile:
    user_id: int
    threads: dict[int, ThreadState]
    started_at_iso: str
    last_updated_iso: str

    @classmethod
    def load_or_init(cls, path: Path, user_id: int, threads_seed: list[dict]) -> "ProgressFile":
        if path.exists():
            data = json.loads(path.read_text())
            states = {int(k): ThreadState(**v) for k, v in data["threads"].items()}
            # Add any newly-discovered threads not in the existing state.
            for t in threads_seed:
                if t["thread_id"] not in states:
                    states[t["thread_id"]] = ThreadState(
                        thread_id=t["thread_id"],
                        thread_slug=t["thread_slug"],
                        title=t.get("title", ""),
                    )
            return cls(
                user_id=user_id,
                threads=states,
                started_at_iso=data.get("started_at_iso", _now_iso()),
                last_updated_iso=_now_iso(),
            )
        states = {
            t["thread_id"]: ThreadState(
                thread_id=t["thread_id"],
                thread_slug=t["thread_slug"],
                title=t.get("title", ""),
            )
            for t in threads_seed
        }
        return cls(user_id=user_id, threads=states, started_at_iso=_now_iso(), last_updated_iso=_now_iso())

    def save(self, path: Path) -> None:
        self.last_updated_iso = _now_iso()
        payload = {
            "user_id": self.user_id,
            "started_at_iso": self.started_at_iso,
            "last_updated_iso": self.last_updated_iso,
            "summary": self._summary(),
            "threads": {str(tid): asdict(s) for tid, s in self.threads.items()},
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        tmp.replace(path)

    def _summary(self) -> dict:
        from collections import Counter
        c = Counter(s.status for s in self.threads.values())
        return {
            "total": len(self.threads),
            "pending": c.get("pending", 0),
            "done": c.get("done", 0),
            "failed": c.get("failed", 0),
            "posts_total": sum(s.posts_total for s in self.threads.values()),
            "images_ok": sum(s.images_ok for s in self.threads.values()),
            "images_failed": sum(s.images_failed for s in self.threads.values()),
        }


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _setup_signals(saver):
    def handler(signum, frame):
        LOG.warning("received signal %d — flushing progress and exiting", signum)
        saver()
        sys.exit(130)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id", type=int, help="numeric forum user id (e.g. 11 for meizzwang)")
    ap.add_argument("--skip-images", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="process at most N pending threads")
    ap.add_argument("--retry-failed", action="store_true",
                    help="retry threads previously marked failed")
    ap.add_argument("--from-thread-id", type=int, default=None,
                    help="start at this thread id (skip earlier ones)")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    raw_root = REPO_ROOT / "data" / "raw"
    parsed_root = REPO_ROOT / "data" / "parsed"
    images_root = REPO_ROOT / "data" / "images"

    discovered_path = parsed_root / "users" / str(args.user_id) / "threads.json"
    if not discovered_path.exists():
        print(f"FAIL: no discovery file at {discovered_path}", file=sys.stderr)
        print("  run: python scripts/discover_user_threads.py <user_id>", file=sys.stderr)
        return 2

    discovered = json.loads(discovered_path.read_text())
    threads_seed = discovered["threads"]

    progress_path = parsed_root / "users" / str(args.user_id) / "archive_progress.json"
    progress = ProgressFile.load_or_init(progress_path, args.user_id, threads_seed)

    fetcher = Fetcher(raw_root=raw_root)
    image_mirror = None if args.skip_images else ImageMirror(images_root=images_root)

    _setup_signals(lambda: progress.save(progress_path))

    todo = [s for s in progress.threads.values() if s.status == "pending"]
    if args.retry_failed:
        todo += [s for s in progress.threads.values() if s.status == "failed"]
    if args.from_thread_id is not None:
        todo = [s for s in todo if s.thread_id >= args.from_thread_id]
    todo.sort(key=lambda s: s.thread_id)
    if args.limit:
        todo = todo[:args.limit]

    summary = progress._summary()
    print(f"=== archive run starting ===")
    print(f"  user_id: {args.user_id}")
    print(f"  total discovered: {summary['total']}")
    print(f"  already done:     {summary['done']}")
    print(f"  failed (prior):   {summary['failed']}")
    print(f"  pending:          {summary['pending']}")
    print(f"  to process now:   {len(todo)}")
    print(f"  skip_images:      {args.skip_images}")
    print()

    if not todo:
        print("nothing to do.")
        return 0

    started_run_at = time.time()
    aborted = False
    for i, state in enumerate(todo, start=1):
        state.started_at_iso = _now_iso()
        try:
            result = archive_thread(
                thread_id=state.thread_id,
                thread_slug=state.thread_slug,
                raw_root=raw_root,
                parsed_root=parsed_root,
                images_root=images_root,
                fetcher=fetcher,
                image_mirror=image_mirror,
                skip_images=args.skip_images,
            )
        except FetchAborted as e:
            state.status = "failed"
            state.error = f"FetchAborted: {e}"
            state.completed_at_iso = _now_iso()
            progress.save(progress_path)
            LOG.error("fetch aborted: %s — stopping run", e)
            aborted = True
            break
        except Exception as e:
            state.status = "failed"
            state.error = f"{type(e).__name__}: {e}"
            state.completed_at_iso = _now_iso()
            progress.save(progress_path)
            LOG.exception("thread %d crashed", state.thread_id)
            continue

        state.pages_fetched = result.pages_fetched
        state.posts_total = result.posts_total
        state.images_ok = result.images_ok
        state.images_failed = result.images_failed
        state.images_attempted = result.images_attempted
        state.parser_warnings = result.parser_warnings
        state.completed_at_iso = _now_iso()
        if result.pages_fetched > 0 and result.posts_total > 0:
            state.status = "done"
        else:
            state.status = "failed"
            state.error = "no pages or no posts parsed"

        progress.save(progress_path)

        elapsed = time.time() - started_run_at
        rate = i / elapsed if elapsed > 0 else 0
        eta_s = (len(todo) - i) / rate if rate > 0 else 0
        print(
            f"[{i:4d}/{len(todo)}] {state.thread_id:>5} {state.title[:60]:<60} "
            f"pages={state.pages_fetched} posts={state.posts_total} "
            f"imgs={state.images_ok}/{state.images_attempted} "
            f"({elapsed/60:.1f}m elapsed, eta ~{eta_s/60:.0f}m)"
        )

    final = progress._summary()
    print()
    print(f"=== run {'ABORTED' if aborted else 'complete'} ===")
    for k, v in final.items():
        print(f"  {k}: {v}")
    return 0 if not aborted else 1


if __name__ == "__main__":
    sys.exit(main())
