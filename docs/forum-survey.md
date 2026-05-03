# sarracenia.proboards.com — structural survey

Read-only reconnaissance, 2026-05-03. Pages saved in `scratch/survey/`
(gitignored). Goal: understand the forum's shape so we can design the
data model, not to begin archival.

## Forum layout

- 56 sub-boards under the root index. Topical breakdown:
  - **Per-species Sarracenia boards:** alata, flava, leucophylla, minor,
    oreophila, panmixia, psittacina, purpurea, rubra, wild
  - **Cross-cutting Sarracenia boards:** hybrids, propagation/cultivation,
    science, group projects, growing from seed, rot, common pests/diseases
  - **Other CPs:** carnivores (general), bog plants, non-carnivores,
    orchids
  - **Photo/community:** plant pics, monthly pictures, plant-of-the-month,
    monthly photo contest, art, plant identification, recommendations,
    introductions, general board, events, conservation, ideas/suggestions,
    administrative
  - **Year archives** (likely sale/trade by year): 2012-2024
  - **Trade-related:** sale-trade, permanent-offerings, temporary-offerings,
    giveaways, wanted-looking, auction, grow-lists
  - **Other:** seed-divtober (oct 2-16), sarracenia-shirt-boards,
    vegetable-garden (Mike's only non-CP-thread he started)

URL pattern: `/board/<id>/<slug>`

## Mike (`meizzwang`) — user 11

- Profile URL: `/user/11`
- Threads-started listing: `/user/11/recent_threads` — paginated, **37
  pages**. Default 25 threads per page → roughly **~900 threads started**.
  This is the spine of the wiki.
- Recent posts listing: `/user/11/recent_posts` (similar shape)
- Sample of thread titles he started (clear clone-description pattern):
  - `flava var rubricorpora 'claret'`
  - `flava var atropurpurea waccamaw`
  - `flava var ornata improved`
  - `moorei effini, okaloosa fl`
  - `flava var cuprea botanique chocolate`
  - `flava atropurpurea dark throat okaloosa`
  - `leucophylla redrum baldwin al`
  - `purpurea ssp. clinton mi`
  - `alata lamar ms`
  - `cephalotus follicularis western venom`
  - `cephalotus follicularis walpole ck`
  - `purpurea ssp. strafford nh`
  - `minor okefenokeensis 'ultimate giant' ware`
  - `sarracenia ellie wang`
  - `sarracenia charlesmoorei`
  - `montana clone 1, transylvania nc`
  - `flava var rubricorpora clone 'liberty'`
  - `report on various different venus clones` (probably a multi-clone roundup)

Naming convention is very consistent: `<species> <variety/subspecies>
<clone-name-or-location>`, often with `<county> <state-abbrev>` for
location-collected wild clones.

## Thread structure

URL pattern: `/thread/<id>/<slug>`, paginated as `?page=N` (~30 posts/page).

- Sample 1: `/thread/5722/leucophylla-redrum-baldwin-al` — single page,
  12 posts, 12 distinct authors. Mike posts, others reply.
- Sample 2: `/thread/3115/sarracenia-ellie-wang` — multi-page thread
  (page 1 had 30 posts).
- Posts have stable IDs: markup contains `id="post-<N>"`.
- Author attribution: `<a class="o-user-link ... user-<userid>"
  data-id="<userid>" title="@<username>">...`. So we can mechanically
  filter posts to just Mike's contributions.

## Image hosting (CRITICAL for archival)

Counted across two sample threads:

| Host | Notes |
|---|---|
| `live.staticflickr.com`, `farm*.staticflickr.com` | Vast majority — 13/18 in one thread, 29/31 in the other. Flickr-hosted. |
| `i*.photobucket.com` | A handful — Photobucket has largely degraded; many old links may be dead. |
| `storage.googleapis.com` | Likely proboards' own attachment storage. |

**Implication:** photos are NOT stored by proboards itself. They live on
third-party services that can disappear (Photobucket already has). For
this archive to actually preserve the visual record, we must mirror the
images locally during capture.

## robots.txt — !! READ BEFORE PROCEEDING !!

Saved to `scratch/survey/robots.txt`. Key clauses:

1. **Anthropic is named-and-blocked.** `anthropic-ai` and `ClaudeBot`
   user-agents are `Disallow: /`. Many other AI/scraper bots likewise.
2. **For generic clients (`User-agent: *`)** the disallow list includes:
   - `/user/` ← *we already fetched /user/11, /user/11/recent_posts,
     /user/11/recent_threads as part of this survey.* Five requests total
     to disallowed paths, with a generic Mozilla UA. We should pause.
   - `/threads/recent`, `/posts/recent`, `/members`
   - `/login/`, `/post/`, `/message/`, `/search/`, `/calendar/`,
     `/conversation/`, `/admin`
3. **Allowed for `*`:** `/`, `/board/<id>/...`, `/thread/<id>/...` (the
   actual content pages). No crawl-delay specified for `*`.

### What this means for the project

Mike's permission as a content author is necessary, but the **forum host
has explicitly opted out of automated archival**, including by Anthropic
specifically. This is a real conflict that needs resolution before we
build any pipeline. Options:

1. **Stop here and get explicit permission from the proboards forum
   owner/admin** (the person who runs sarracenia.proboards.com — possibly
   Mike himself? possibly not). Their robots.txt is them speaking.
2. **Ask Mike to export his own posts/threads via proboards' user
   data export** (if available) — that bypasses the scraping question
   entirely because it's first-party data access by the account owner.
3. **Manual / human-driven capture** — Mike opens threads in his browser
   and saves them, or we ask him to send us the content. Slow but
   unambiguous.
4. **Limit automated fetching to the paths allowed in robots.txt
   (`/board/`, `/thread/`)**, accept that `/user/` enumeration is off
   limits, and identify Mike's threads via the board listings instead.
   Lower friction but still operating against the spirit of the named-
   bot block.

My recommendation: **option 2 first, then 4 only if 2 isn't possible,
and only after the forum owner is told what we're doing.**

## Numbers we now know

- ~900 threads started by Mike across 37 pages of his thread history
- 12-30+ posts per thread (rough sample)
- ~10-30 images per clone thread (Flickr-hosted)
- Forum has been active 2012-present (year-archive boards span 2012-2024)

That's plenty to scope effort: this is a small archive (low thousands of
posts, low tens of thousands of images) — entirely tractable, but worth
doing carefully once.
