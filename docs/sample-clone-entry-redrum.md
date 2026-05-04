# Sample clone entry — `S. leucophylla 'REDRUM'`

This is a **hand-drafted example** of what a per-clone wiki entry could
look like, derived from the parsed forum bundle for thread 5722. The
goal is to give Mike a concrete artifact to react to before we lock in
the schema for the synthesis layer. **Nothing here is canonical.**
Items marked **[VERIFY]** are guesses extracted from forum text and
need Mike's confirmation; **[MISSING]** are fields the source thread
doesn't cover and must come from Mike or other threads.

---

## Proposed schema (per clone)

```yaml
# Identity
full_name: "Sarracenia leucophylla 'REDRUM'"   # genus + species [+ var/ssp] + cultivar
short_name: "REDRUM"                            # the cultivar/clone name alone
species: "leucophylla"
infraspecific_rank: null                        # var. / ssp. / f. / x   (null if none)
infraspecific_name: null
genus: "Sarracenia"
hybrid: false                                   # true if 'x' / inter-species

# Provenance
origin_locality:
  county: "Baldwin"
  state: "AL"
  country: "USA"
  notes: ""                                     # free text (e.g., "site #2", "near X creek")
collector: null                                 # [MISSING] — who originally collected the wild plant
breeder: null                                   # null for wild clones; person/org for cultivars
year_collected: null                            # [MISSING] — when removed from the wild
year_described: 2022                            # year the name was first published in this archive (first thread-1 post)
year_into_cultivation: ~2012                    # [VERIFY] — Mike says "a good decade" of overcrowding before 2022 transplant
naming_etymology: |
  "Murder" written backwards, after the catchphrase from The Shining.
  Named for the blood-red trap color. ([VERIFY] — confirmed by Mike in
  post id=48907)

# Description
standout_traits:
  - "Brilliant red trap color, especially in fall pitchers"
  - "Distinctive bulge at the back of the trap"
  - "Significant white area at the top of the trap"
  - "Older summer traps can darken further with age"
visually_similar_to:
  - clone: "Wilkerson's Red Rocket"
    note: "appearance is similar but origin is unrelated"

# Cultivation
cultivation_notes: |
  Held in a community tray for roughly a decade before being transplanted
  (winter ~2020/2021). After transplanting, produced its first impressive
  fall pitchers in 2022. In Mike's collection, fall traps on this clone
  open about 1-2 weeks earlier than most other leucophylla clones —
  Mike attributes this to a warmer soil-temperature microclimate at the
  front of the community tray. Spring traps are usually unimpressive
  for this clone in Mike's climate, but during the unusually hot March
  2026 (92°F highs) it produced atypically nice spring pitchers.

# Sources
source_threads:
  - thread_id: 5722
    url: "https://sarracenia.proboards.com/thread/5722/leucophylla-redrum-baldwin-al"
    role: "primary"

# Photographs (a curated subset from the source threads)
photos:
  - local: "ba/ba326d9c1afbf9c346eb50f78c837c6040be09e4a2de371301177eab7c46ff4b.jpg"
    caption: "Initial introduction photos, taken 9/1/22"
    photographer: "Mike Wang"
    source_post_id: 48899
  - local: "f4/f4368c3ea5e61c9d8a850e9a95354c61d560a10b45a73dac1a700e8d038e5ad1.jpg"
    caption: "Detail showing the distinctive back-of-trap bulge"
    photographer: "Mike Wang"
    source_post_id: 48899
  # ... etc — 13 total photos available in the thread

# Review state
review:
  ai_extracted_at: "2026-05-04T14:00:00Z"
  human_reviewed: false
  human_reviewer: null
  human_corrections: []
  open_questions:
    - "Who collected the original wild plant? Mike implies it's not from the
       Wilkerson property — which Baldwin Co. site does it come from?"
    - "When did Mike receive the clone, and from whom?"
    - "Confirm the ~2012 'into cultivation' inference is right (or replace
       with the actual date)."
```

## Why YAML frontmatter (or sidecar)

- Human-readable + machine-readable.
- Each clone is one file, version-controllable in git.
- The body (below the `---`) can be free-form Markdown for narrative
  and image gallery, while the structured top stays queryable.

## Open design questions to discuss with Mike

1. **Granularity of "clones":** is REDRUM one entry, or does it sit
   under a parent `S. leucophylla` page with REDRUM as a sub-entry?
2. **Multiple threads per clone:** many clones probably appear in
   several threads over the years (introduction + updates + sale). The
   schema needs `source_threads[]` and a way to merge information
   across them.
3. **Field set:** is the proposed list complete? Mike originally listed
   "origin / history / traits / full name / location / photos /
   cultivation notes" — current schema covers all of those plus
   etymology, naming, breeder/collector, similar clones.
4. **Unverified data policy:** how loud should the "[VERIFY]" markers
   be in the rendered wiki? My current vote: visible to readers as
   small badges so the wiki never accidentally presents a guess as a
   fact, until Mike has reviewed.
5. **Photo curation:** all forum photos (10–30+ per thread)? A curated
   subset Mike picks? An algorithmic top-N? My vote: surface them all
   in a per-clone gallery, mark Mike's "favorites" if he flags them.
