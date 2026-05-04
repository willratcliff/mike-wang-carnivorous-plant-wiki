# Clone-page synthesis recipe

This document defines the *exact* process I follow when writing a per-clone
wiki entry. Following the same recipe every time keeps the output uniform
and reviewable.

## Inputs

- One **clone cluster** from `data/parsed/clones/clusters.json` —
  `{cluster_id, candidate_name, source_thread_ids, ...}`
- For each `source_thread_id`, the **thread bundle** at
  `data/bundles/threads/<id>.md` (rendered Markdown — Mike's posts
  highlighted, images locally mirrored).

## Output

`wiki/<genus>/<species_or_x>/<clone_slug>/index.md`

Where:
- `<genus>` is lowercase Latin (`sarracenia`, `cephalotus`, ...).
- `<species_or_x>` is the lowercase Latin species (`leucophylla`,
  `flava`) or `hybrids` for inter-species crosses.
- `<clone_slug>` is a slugified version of the cultivar name +
  optional location tag, e.g. `redrum-baldwin-al`.

If a clone has multiple infraspecific levels (`var. alba`), nest under
the species: `wiki/sarracenia/leucophylla/var-alba/<clone_slug>/`.

## File structure

```markdown
---
# Identity
full_name: "Sarracenia leucophylla 'REDRUM' Baldwin Co, AL"
short_name: "REDRUM"
genus: "Sarracenia"
species: "leucophylla"
infraspecific_rank: null              # var. / ssp. / f. / x / null
infraspecific_name: null
hybrid: false

# Provenance
origin_locality:
  county: "Baldwin"
  state: "AL"
  country: "USA"
  notes: ""
collector: null                       # who pulled it from the wild
breeder: null                         # null for wild clones
year_collected: null
year_into_cultivation: null
year_first_described_on_forum: 2022   # date of earliest source-thread post
naming_etymology: ""

# Description
standout_traits:
  - "..."
visually_similar_to:
  - clone: "..."
    note: "..."

# Cultivation
cultivation_notes: |
  ...

# Sources
source_threads:
  - thread_id: 5722
    url: "https://sarracenia.proboards.com/thread/5722/leucophylla-redrum-baldwin-al"
    role: "primary"             # primary | update | sale | photos | passing-mention

# Photographs (referenced from data/images/<sha-prefix>/<sha>.<ext>)
photos:
  - path: "ba/ba326d9c1afbf9c346eb50f78c837c6040be09e4a2de371301177eab7c46ff4b.jpg"
    caption: "..."
    photographer: "Mike Wang"
    source_post_id: 48899
    favorite: false             # mark true if Mike flags it

# Review state
review:
  ai_extracted_by: "Claude (Claude Code session, 2026-05-04)"
  ai_extracted_at: "2026-05-04T...Z"
  cluster_id: "C0001"
  human_reviewed: false
  human_reviewer: null
  human_corrections: []
  open_questions:
    - "..."
---

# {full_name}

## Origin

{narrative paragraph extracting origin info from the source threads,
with [VERIFY] markers on inferences and [MISSING] on gaps}

## History

...

## Standout traits

...

## Cultivation notes

...

## Photos

{full gallery, one per `photos` entry, captions visible}

## Sources

{bulleted list of source threads with links}

---

*This entry was AI-extracted from forum posts and is awaiting human
review. Items marked `[VERIFY]` are inferences; items marked `[MISSING]`
require additional input from Mike Wang.*
```

## Extraction rules

1. **Mike-only when in doubt.** When extracting facts from the bundle,
   prefer statements made by `meizzwang` (highlighted as **Mike Wang**
   in bundles). Other forum members' replies can suggest open questions
   but should not be elevated to facts.

2. **No invention.** If the source thread doesn't mention something,
   leave the field `null` and add an `open_questions` entry. Do not
   guess values.

3. **Inferences are tagged.** When extracting a fact requires
   interpretation (e.g., "a good decade of being overcrowded" → ~10
   years to cultivation), record the value AND tag it `[VERIFY]` in the
   narrative.

4. **Direct quotes for traits.** Copy Mike's own descriptive language
   into `standout_traits[]` where possible — he's the authority on what
   each clone looks like.

5. **Cross-thread integration.** When multiple `source_threads`, walk
   them chronologically. Conflicting information becomes
   `open_questions`, not silent overwriting.

6. **Photos: include all of Mike's.** Pull every `image_urls` entry
   from Mike's posts into `photos[]`, with captions from surrounding
   text (best-effort) and `favorite: false` (Mike flags later). Skip
   broken/not-mirrored entries — they remain in the source bundle for
   reference but don't appear in the curated gallery.

7. **Slug generation:** lowercase, replace spaces with `-`, strip
   non-alphanumeric except `-`. Append a county-state suffix only when
   needed for disambiguation.

## Per-cluster checklist

For each cluster:

1. Look up the cluster in `clusters.json`.
2. Read every `data/bundles/threads/<id>.md` for the cluster's threads.
   Use the **6-digit zero-padded** path: `data/bundles/threads/000957.md`,
   not `957.md`.
3. **Decide if this cluster is one clone or several.** Read the
   "Cultivar-group splits" section below before assuming the cluster
   is one entry.
4. Determine genus/species path; create the wiki directory.
5. Write `index.md` per the structure above.
6. Update `data/parsed/clones/synthesis_progress.json` with the result
   (status `done`, `wrote_to[]` paths, optional `split_decision` text).
7. Validate by re-reading the file. Watch for: image paths exist on
   disk under `data/images/`, all `[VERIFY]`/`[MISSING]` markers
   intentional, source post IDs match the bundle.

## Cultivar-group splits — IMPORTANT

A single cluster from `clusters.json` may describe **multiple distinct
genetic individuals** that share a cultivar/locality name. Three real
examples seen so far:

- **`'Sand Mountain'`** (S. oreophila var. ornata): two clones in this
  cultivar group — Mike's "Clone A" (long-cultivated, 2012+) and a
  separately-imported "European clone" (2013).
- **`'Brewer's Red'` vs `'Brewer's Beauty'`** (Cephalotus): genuinely
  different cultivar names that the title-parser merged into a single
  cluster due to a regex bug (now fixed). Always check the source
  thread titles before trusting the cluster's `candidate_name`.
- **`'best clone'`** (S. montana Transylvania Co NC): Mike applied
  the same informal label to two genetically distinct individuals —
  the M.R.-acquired plant (pre-2013) and an HxC seedling Mike grew
  out after the 2014 fungal die-off.

**Signals that you're looking at multiple clones, not one:**

- Thread titles include "Clone A" / "Clone B" / numeric or letter
  designators ("Clone E", "Clone X", etc.)
- One thread says "European clone" / "California clone" / mentions a
  different acquisition source than the other
- One thread's history starts with "Mike acquired in <year>" and the
  other says "I grew this out from seed"
- The "candidate_name" looks truncated (might be a regex bug — see
  the lessons section below)
- Different parentage / breeders mentioned

**When you split, the layout is:**

```
wiki/<genus>/<species>/<cultivar-group-slug>/
  index.md                  ← cultivar-group parent (type: cultivar_group)
  <clone-slug-1>/
    index.md                ← per-clone entry, with cultivar_group field
  <clone-slug-2>/
    index.md
```

The parent `index.md` has minimal frontmatter (`type: cultivar_group`,
member_clones list, note explaining the split) and links to children.

Document the split in `synthesis_progress.json` with a `split_decision`
field describing why so future readers can audit the call.

## Schema additions discovered during synthesis

These are fields beyond the original sample schema that earned their
keep across multiple entries:

- **`cultivar_group`** (in per-clone frontmatter): the shared cultivar
  name when this clone is part of a group. Empty/null for solo clones.
- **`photos_not_mirrored`** (top-level): for source posts whose images
  are referenced as outbound URLs (postimg.cc, plain Flickr links)
  rather than embedded `<img>` tags — the image_mirror won't have
  picked them up. List `{source_post_id, note}` so a future improvement
  can chase them.
- **`review.cluster_split_note`** (when split): plain-language
  explanation of why this cluster was split. Surfaces in the rendered
  wiki to keep the decision auditable.
- **`visually_similar_to[]`**: keep this; multiple entries used it
  ("Wilkerson's Red Rocket" comparisons; "California Carnivores Sand
  Mountain" possible-same-clone reference).

## Cross-thread integration rules

When synthesizing across multiple `source_threads`:

- **Walk threads in chronological order** of first Mike-post timestamp.
- **Don't silently overwrite.** When thread N's history conflicts with
  thread M's, both go in `open_questions[]` with their respective
  source post IDs.
- **Photos accumulate**, not replace. Each thread's Mike-photos all
  go into `photos[]` with `source_post_id` pointing to the original.
- **Cultivation notes are time-stamped.** When Mike's recommended
  approach evolves (e.g., "I now keep it growing in zero standing
  water"), include the year of the latest advice rather than picking
  one statement. Phrasing: "Mike's 2017 update: ..."
- **Etymology and origin are usually first-thread.** The introduction
  thread typically establishes the name and the wild-collection
  context. Updates rarely revise these — but check.

## Other gotchas seen so far

- **Board placement may be wrong.** Mike's *S. montana* threads live
  under the `Sarracenia purpurea` board (board id 21) because in older
  taxonomy *montana* was treated as a *purpurea* subspecies. Trust the
  *thread title* for genus/species identification, not the board.
- **External-host images are common.** Many older threads link to
  postimg.cc, photobucket, or plain flic.kr URLs as outbound links
  rather than embedded `<img>` tags. The image mirror won't have
  these. Use `photos_not_mirrored[]` to record them so they're not
  silently lost.
- **Forum reply quotes embed full image references.** When a member
  quotes Mike's earlier post, the same image appears twice in the
  bundle (once in Mike's original post, once in the quote). Don't
  add the quoted version to `photos[]` — only the original Mike-post
  source.
- **"Best clone", "best of batch", "Clone A"** are informal Mike
  labels, not formal cultivars. The title-parse catalog treats them
  as cultivars — that's correct for clustering purposes, but be
  cautious: these names get re-used for different plants over time.
- **Smileys and avatars** were filtered from the parser's
  `image_urls`, but a few `storage.proboards.com` paths slip through.
  These appear with `[not mirrored]` tags in bundles; don't include
  them in `photos[]`.
