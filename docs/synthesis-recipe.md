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
3. Determine genus/species path; create the wiki directory.
4. Write `index.md` per the structure above.
5. Update `data/parsed/clones/synthesis_progress.json` with the result.
6. Validate by re-reading the file (frontmatter parses as YAML).
