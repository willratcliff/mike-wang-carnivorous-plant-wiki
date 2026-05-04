# Session startup: continuing the carnivorous-plant-clone wiki

**Read this first if you are a Claude Code session picking up this
project.** It tells you what's done, what's next, and how to maintain
quality. Skim time: ~3 minutes.

---

## What this project is

A wiki of carnivorous plant clones described by **Mike Wang** on the
forum at <https://sarracenia.proboards.com>. Mike (forum admin,
username `meizzwang`, user id 11) requested this archive because the
forum could go down and he wants the clone history preserved.

**Permission to archive:** see `docs/permission.md` — Mike's verbatim
written grant. He overrides the site's `robots.txt` block on AI bots
specifically for this project.

**Lab-assistant guidelines** in the user's `CLAUDE.md` apply: be
human-in-the-loop, don't make scientific assumptions, ask before
deciding methodology. The user has waived oversight for routine
synthesis work, but you should still flag genuinely novel design
decisions. Mike is the authoritative reviewer for every clone entry.

## What's done

| Phase | Output | Status |
| --- | --- | --- |
| Forum survey | `docs/forum-survey.md` | done |
| Discover Mike's threads | `data/parsed/users/11/threads.json` (925 threads) | done |
| Phase 1: archive HTML + parse | `data/raw/threads/<id>/page-N.html`, `data/parsed/threads/<id>/page-N.json` | done — 925/925, 9939 posts |
| Phase 2: mirror images | `data/images/<sha-prefix>/<sha>.<ext>`, `data/images/manifest.json` | done — 16,973/17,721 (95.8%), 3.6 GB |
| Per-thread Markdown bundles | `data/bundles/threads/<id>.md` | done — 925 bundles |
| Title-parse catalog | `data/parsed/users/11/title_catalog.json` | done — 797 clone-candidates |
| Cluster threads by clone | `data/parsed/clones/clusters.json` | done — 791 clusters (6 multi-thread, 785 singletons, 128 non-clone) |
| Synthesis: write wiki entries | `wiki/<genus>/<species>/.../<clone>/index.md` | **in progress — 2 clusters / 4 entries done** |
| Static site generator | `_site/` (planned) | not started |

Read `data/parsed/clones/synthesis_progress.json` for the authoritative
"what's been synthesized" list.

## How to continue synthesis (the main remaining work)

### Step 1: Pick the next cluster

```bash
.venv/bin/python -c "
import json
clusters = json.load(open('data/parsed/clones/clusters.json'))['clusters']
done = json.load(open('data/parsed/clones/synthesis_progress.json'))['clusters']
done_ids = set(done.keys())
# Suggested order: multi-thread first, then singletons
todo = [c for c in clusters if c['cluster_id'] not in done_ids and not any(d.startswith(c['cluster_id']) for d in done_ids)]
todo.sort(key=lambda c: (-c['thread_count'], c['cluster_id']))
for c in todo[:5]:
    print(f\"  [{c['cluster_id']}] {c['thread_count']:>2}t  {c['candidate_name']}\")
"
```

Pick one. Multi-thread clusters first — they're the highest value
because cross-thread integration is the synthesis layer's main job.

### Step 2: Read the bundles

For every thread in `cluster.source_thread_ids`, read its bundle:

```
data/bundles/threads/<6-digit-padded-id>.md
```

The bundle is the human-readable mirror of the thread, with Mike's
posts highlighted as **Mike Wang**, replies in *italic*, and image
references rewritten to local paths (or tagged `[broken]` /
`[not mirrored]`).

### Step 3: Write the wiki entry/entries

Follow `docs/synthesis-recipe.md` precisely. Key rules:

1. **Directory layout:** `wiki/<genus>/<species_or_x>/<infra-prefix>/<clone-slug>/index.md`
   - Genus and species lowercase Latin (`sarracenia`, `oreophila`).
   - Infraspecific names get a directory if the variety/subspecies
     groups multiple clones: `var-ornata/sand-mountain/clone-a/`.
   - For hybrids without species: `wiki/<genus>/hybrids/<clone-slug>/`.
2. **YAML frontmatter** matching the schema in
   `docs/sample-clone-entry-redrum.md`. Fields: identity, provenance,
   description, cultivation, sources, photos (one per Mike-photo URL,
   with caption + source_post_id), review state.
3. **Inferences are tagged.** Use `[VERIFY]` for guessed values.
4. **Missing data is flagged.** Use `[MISSING]` and add an
   `open_questions` entry.
5. **Mike-only when in doubt.** Don't elevate other forum members'
   statements to facts.
6. **No invention.** Empty fields are fine.

### Step 4: Watch for "split" cases

Two clones can share a cultivar name. When you read the bundles, look
for signals like:
- "Clone A", "Clone B", numbered designators
- "European clone" / "California clone" / a different acquisition source
- Different wild-collection counties under the same cultivar group

If you see this, **split the cluster** into per-clone entries under a
**cultivar-group parent page** — the pattern established by Sand
Mountain in `wiki/sarracenia/oreophila/var-ornata/sand-mountain/`.

Document the split decision in `synthesis_progress.json` so it's
auditable.

### Step 5: Update the progress tracker

Edit `data/parsed/clones/synthesis_progress.json` with an entry like:

```json
"C0221": {
  "candidate_name": "Sarracenia montana 'best clone' Transylvania Co, NC",
  "source_thread_ids": [957, 5291],
  "status": "done",
  "wrote_to": ["wiki/sarracenia/montana/best-clone/index.md"],
  "completed_at_iso": "<UTC ISO>",
  "notes": ""  // any flags for human reviewers
}
```

### Step 6: Commit

```
git add wiki/ data/parsed/clones/synthesis_progress.json
git commit -m "Synthesize: <clone-name> (cluster <id>)"
```

Use the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
footer. Don't push without permission (project may not have a remote
yet).

## Quality bar

- **Mike's voice preserved.** Quote his descriptive language directly
  in `standout_traits[]` rather than paraphrasing.
- **Photo gallery is comprehensive.** Every Mike-uploaded image goes
  into `photos[]`, even if there are 30 of them, with the best caption
  inferable from surrounding text. `favorite: false` by default —
  Mike will flag favorites later.
- **Cross-thread integration.** When multiple `source_threads`,
  walk them in chronological order. Conflicts become `open_questions`,
  not silent overwrites.
- **No fictional dates.** If Mike says "a few years back" or "a
  decade", record `[VERIFY]` with the inferred year and quote the
  original phrasing so a reviewer can check.

## Pacing reality

At careful-quality pace, expect roughly **5-8 clones per session**
before context pressure builds. There are 791 clusters, so this is
many sessions. That's fine — the work compounds:

- The 6 multi-thread clusters are highest value (synthesis is the
  only way to integrate them).
- Then singletons can be batched by species (do all of `leucophylla`
  in a few sessions, then `flava`, etc.) so a future session has
  context efficiency.
- Mike will review entries as they land; corrections compound too.

If you finish a session, make sure `synthesis_progress.json` is
up-to-date and committed. Leave a brief "what's next" note in the
final commit message so the next session sees it in `git log`.

## Things to watch for (lessons from prior sessions)

- **Cultivar regex bug (fixed).** Possessive apostrophes in cultivar
  names ("Brewer's Red") used to break the parser; fix in commit
  `ef30f4a`. If you see suspicious cluster names that look truncated,
  re-run `scripts/extract_title_catalog.py` and `scripts/cluster_clones.py`.
- **Cultivar-group splits.** See "Step 4" above. Sand Mountain and
  Brewer were both split. More are likely.
- **Photobucket / TinyPic dead images.** Many old photos are 404. The
  manifest records this; the wiki entries should not reference broken
  paths in the curated `photos[]` list.
- **The thread bundle has post numbers AND post IDs.** Use post IDs
  (e.g., `id=48899`) when citing source posts in the wiki, not the
  per-bundle post number which depends on rendering.
- **Bundle paths** use 6-digit zero-padded thread IDs:
  `data/bundles/threads/000254.md`, not `data/bundles/threads/254.md`.
- **The `wiki/` tree is the user-facing artifact.** `data/` is
  intermediate. Don't put narrative content in `data/`.

## Files to know

```
docs/
  permission.md              — Mike's archival permission grant (verbatim)
  forum-survey.md            — initial structural survey of the forum
  synthesis-recipe.md        — exact recipe for writing a wiki entry
  sample-clone-entry-redrum.md — schema discussion artifact
  session-startup.md         — this file

src/sarrwiki/                — Python archive tooling
  fetcher.py                 — polite HTML fetcher (curl-based)
  parser.py                  — proboards thread/post parser
  image_mirror.py            — sha256-content-addressed image cache
  pipeline.py                — fetch → parse → mirror per thread
  title_parse.py             — title -> {genus, species, cultivar, ...}
  bundle.py                  — render parsed thread to Markdown

scripts/                     — driver scripts
  archive_one_thread.py      — smoke test
  archive_user_threads.py    — bulk: all threads by a user (resumable)
  discover_user_threads.py   — list threads started by a user
  mirror_all_images.py       — image mirroring (resumable)
  reparse_warned_threads.py  — re-run parser on cached HTML
  build_thread_bundles.py    — render all bundles
  extract_title_catalog.py   — title-parse all discovered threads
  cluster_clones.py          — group threads into clone clusters
  corpus_stats.py            — diagnostic stats

data/
  raw/threads/<id>/page-N.html
  parsed/threads/<id>/page-N.json
  parsed/users/11/{threads,title_catalog,archive_progress}.json
  parsed/clones/{clusters,synthesis_progress}.json
  images/<sha-prefix>/<sha>.<ext>
  images/manifest.json
  bundles/threads/<id>.md, index.md

wiki/                        — the user-facing wiki tree (output)
  <genus>/<species>/.../<clone>/index.md
```

## When to stop and ask

- The synthesis-recipe rules are not enough to decide something.
- A bundle suggests a cultivar that maps to 5+ unrelated forum threads
  (you may have rediscovered a cluster bug — investigate, don't paper
  over).
- A clone has thread content that contradicts itself across years.
- You're tempted to invent or interpolate a value to fill a field.

When in doubt: leave the field empty, mark `[MISSING]`, surface the
question for Mike. Better an empty entry than a confidently wrong one.
