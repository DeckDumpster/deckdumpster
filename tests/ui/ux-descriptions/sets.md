# Browse Sets — UX Description

Routes: `/sets` (set index) and `/sets/:set_code` (binder grid)
Sources: `mtg_collector/static/sets.html` + `sets.js` + `sets.css`,
`mtg_collector/static/set_browse.html` (self-contained; page script inline)
Served by: `crack_pack_server.py` — `path == "/sets"` → `sets.html`,
`path.startswith("/sets/")` → `set_browse.html` (the set code is read from the
path by the page itself, the way `/card/:set/:cn` does it)

Two pages, one feature, so they are documented together. `/sets` is the across-sets
list; `/sets/:set_code` is the single-set binder the list links into. Neither
filename collides with `sheets.md`, which documents the unrelated `/sheets` booster
sheet explorer.

---

## 1. Page Purpose

**`/sets`** lists every set whose card list is cached locally, grouped by set type in a
fixed order — Expansion, Core, Commander, … — with the sets inside each group newest
release first. A sticky 220 px jump rail down the left names every one of those groups
with its set count and scrolls to it; each group is collapsible, and only the top four
types by curated rank start expanded. Each set is a tile showing its keyrune symbol,
name, code, release date, and up to two completion meters — how much of the base set is
owned, and how much of the whole printing catalogue for that set is owned. It is the
entry point to the binder, and on its own it answers "which sets am I close to
finishing?".

**`/sets/:set_code`** lays one set out as a binder page: every printing in the set, in
collector-number order, at a caller-chosen number of cards per row, with owned pockets
bright and unowned pockets dimmed. Under each card is a row of finish pips (NF / Foil /
Etch), and **one click on a pip adds one copy of that finish** — no modal, no form, no
refetch. Every add of a visit is filed under one batch, created lazily by the first
click, so the whole pass is reviewable afterwards at `/batches/:id`. Clicking the *art*
instead opens the card modal, which is where the finishes get a `−`/count/`+` stepper and
where the condition every add of the visit is filed under is chosen. The page exists to
make reconciling a physical binder against the digital collection cost one click per
card. It is deliberately not a faster search:
`/collection?q=s:fin is:unowned` already answers the query, but it does not lay the set
out as a fixed grid or make adding one copy cheap.

---

## 2. Navigation

### Into the feature

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| "Browse Sets" nav card | `<a>` | `/sets` | Homepage (`index.html`), Analysis group, immediately after "Explore Sheets". Sub-text: "Every set as a binder grid, with completion" |

### `/sets`

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| "DeckDumpster" (header h1) | `<a>` | `/` | `.site-header` from `shared.css` |
| Collection / Decks / Build / Binders / Sealed | `<a>` | `/collection`, `/decks`, `/deck-builder`, `/binders`, `/sealed` | The standard shared header links. There is **no** "Sets" entry in this header |
| Set tile | `<a class="set-tile">` | `/sets/{set_code}` | The whole tile is the link — symbol, name, sub-line and meters are all inside the anchor |
| Jump rail row | `<button class="rail-row">` | same page | Expands the group and scrolls to it. Not a link — there is no hash in the URL and nothing to restore |

### `/sets/:set_code`

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| Scryfall badge per card | `<a class="badge link">` | `https://scryfall.com/card/{set}/{cn}` | New tab. Label "SF" + optional TCG price |
| Card Kingdom badge per card | `<a class="badge link">` | `ck_url` from the API | New tab. Label "CK" + optional CK price |
| "Full page →" (in card modal) | `<a class="badge link">` | `/card/{set}/{cn}` | Same-tab navigation to the card detail page |
| Scryfall / Card Kingdom (in card modal) | `<a class="badge link">` | external | New tab |

This page uses its own dark `<header>`, **not** `.site-header`: there is no shared site
nav bar, no link back to `/sets`, and the `<h1>` (set name + set code) is plain text
rather than a link. The only in-app way out is the browser back button or a card link.

---

## 3. Interactive Elements

### `/sets`

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Set filter | `#set-filter` | `<input type="text">` | Placeholder "Filter by set name or code". `autocomplete="off"`, `spellcheck="false"`. Filters entirely in the browser — it never re-queries the server. Matches a case-insensitive substring of `"{set_name} {set_code}"` |
| Result count | `#sets-count` | `<span>` | Read-only. `"{N} sets"`, or `"{shown} of {N} sets"` while a filter is active |
| Group heading | `.set-group-header` | `<h2 role="button" tabindex="0">` | The collapse control — click, Enter or Space toggles `.open` on the section and flips `aria-expanded`. Holds a rotating caret (a `::before`, so the heading's text still starts with the label), the set-type label, a `.group-count` and a `.group-owned` roll-up, both of which track the filter |
| Jump rail | `#sets-rail` | `<aside>` | `aria-label="Jump to set type"`. One `.rail-row` button per rendered group, in the same order as the sections |
| Jump rail row | `.rail-row` | `<button>` | `data-set-type` names its group. Carries `.rail-label` and a `.rail-count` that tracks the filter; gains `.is-empty` (dimmed) when the filter left its group with nothing |
| Set tile | `.set-tile` | `<a>` | Navigates to the binder for that set. Hover raises the border to the accent colour |
| No-match empty state | `#sets-no-match` | `<div>` | Hidden unless the filter matches zero sets |

### `/sets/:set_code` — header controls

| Element | ID | Type | Description |
|---------|----|------|-------------|
| In-set search | `#q` | `<input type="search">` | Placeholder "Search this set…". 250 ms debounce, then a refetch. Server-side `card.name LIKE %q%` |
| Pocket filter | `#filter` | `<select>` | `all` ("All pockets") / `have` / `need` |
| Sort | `#sort` | `<select>` | `number` (default) / `name` / `rarity` / `price` / `qty` ("Copies") |
| Sort direction | `#order` | `<button class="toggle">` | Text toggles "Asc" ⇄ "Desc"; gains class `on` (accent fill) when Desc |
| Section pills | `#sections` | `<div>` of 3 `<button class="toggle" data-section>` | "Base", "Extended", "Promos". Each toggles class `on`. **The last enabled pill cannot be turned off** — the click is ignored, because the endpoint rejects an empty `sections` and a binder with no sections is not a view |
| Cards-per-row minus | `#col-minus` | `<button class="col-btn">` | Decrements columns; disabled at 1 |
| Cards-per-row count | `#col-count` | `<span>` | Read-only current column count |
| Cards-per-row plus | `#col-plus` | `<button class="col-btn">` | Increments columns; disabled at 12 |
| Status | `#status` | `<div>` | Read-only, right-aligned (`margin-left: auto`). "Loading…", then `"{N} printings"`. Gains class `error` (accent red) on a failed load |
| Review link | `#batch-link` | `<a>` | "Review this pass →". `hidden` until the first add of the visit lands, then points at `/batches/{id}` for that visit's session batch |

### `/sets/:set_code` — grid (dynamically generated)

| Element | Class | Type | Description |
|---------|-------|------|-------------|
| Section header | `.section-header` | `<div>` | Not clickable — unlike `/sheets`, sections here do not collapse. Shows the title and `"{N} printings"` |
| Card grid | `.card-grid` | `<div>` | `grid-template-columns: repeat(var(--grid-cols), 1fr)` |
| Card tile | `.sheet-card` | `<div>` | Carries `data-printing-id`. Its card object is stashed on the element as `el._card` |
| Card art | `.sheet-card-img-wrap` | `<div>` (click target) | Opens the card modal. Adds nothing |
| Finish pip | `.finish-pip` | `<button data-finish>` | **One click adds one copy of that finish.** One pip per entry in `printings.finishes`, plus any finish actually held that the catalogue does not list. Filled pips carry the rarity colour via `--pip-color` and read `"NF"` / `"Foil 3"` etc. |
| Pip failure note | `.pip-error` | `<div>` | Appended to the tile when the add is rejected; carries the server's message |
| Card modal | `.card-modal-overlay` | `<div>` | From `shared-card-modal.js`. Dismissed by clicking the backdrop, the `×` button, or pressing Escape. Contains a flip button for double-faced cards |

Anchors inside a tile (the SF and CK badges) are excluded from the tile's click handler,
so a badge click links out instead of opening the modal.

### `/sets/:set_code` — card modal (dynamically generated)

Everything below is rendered by the page's `renderBinderControls()` and handed to the
shared modal through its `renderExtra` hook. The modal itself is **not** forked; its other
caller, `deck_builder.html`, passes no `renderExtra` and sees none of this.

| Element | Class / id | Type | Description |
|---------|-----------|------|-------------|
| Foil-kind badges | `.badge.foil-kind` | `<span>` | One per entry in `foil_kinds`, under a "Foil kind" section title. Absent when the printing has none |
| Condition select | `#binder-condition` | `<select>` | The five conditions the schema accepts. **Sticky for the whole page visit** — see Flow 2 |
| Finish row | `.binder-finish` | `<div>` | One per entry in the row's `owned` array, i.e. one per finish the printing exists in, empty pockets included |
| Step buttons | `.binder-step` | `<button data-finish data-delta>` | `−` and `+`. The `−` is `disabled` while that finish is held in no copy |
| Finish count | `.binder-count` | `<span data-finish>` | The copies held in that finish; updated in place, never by re-rendering the panel |
| Step failure note | `.binder-error` | `<div>` | Empty (and `display:none`) until a step is rejected; carries the server's message |

The card-detail and CK/TCG links are **not** repeated in this block: the shared modal
already renders "Full page →", SF and CK above it, and a second copy of each would be two
links to the same page.

---

## 4. User Flows

### Flow 1: Find a set

1. User opens `/sets` from the homepage nav. Body shows a spinner and "Loading sets…".
2. `GET /api/sets/index` returns every cached set, newest release first.
3. Tiles render grouped by set type, the groups in `sets.js`'s curated `SET_TYPE_RANK`
   order — Expansion leads whatever was released most recently, and a set type the rank
   has never heard of renders last rather than dropping out. Within a group the sets
   stay newest-first, the order the response arrives in. Count reads `"{N} sets"`.
   Expansion, Core, Commander and Masters are expanded; every other group is collapsed
   to its heading.
4. The jump rail lists the same groups in the same order with their counts. User clicks
   **Token**: the group expands and the page scrolls to it.
5. User types `fin` (or `Final Fantasy`) into the filter. Tiles hide on every keystroke;
   each group heading's count and roll-up update, as does each rail row's count; a group
   that lost every set hides entirely and its rail row dims; a group holding a match
   opens whether it was collapsed or not.
6. Count reads `"{shown} of {N} sets"`. Clearing the filter hands every group back to the
   expanded/collapsed state the user left it in.
7. User clicks a tile and lands on `/sets/{code}`.

### Flow 2: Reconcile a physical binder (the reason the feature exists)

1. `/sets/fin` loads. Base and Extended sections render; Promos are off by default.
2. Owned pockets are bright, unowned pockets are greyed and dimmed.
3. For each card the user physically holds but the app does not, they click the matching
   finish pip once.
4. The pip fills immediately, the copy count on it rises, and — if the pocket was empty —
   the header meters advance by one. No refetch, no page movement.
5. The `POST /api/collection` request follows in the background, carrying the visit's
   session batch and the sticky condition (Near Mint unless the user changed it in the
   modal — see Flow 3a).
6. On the first add a "Review this pass →" link appears in the header; every later add in
   the same visit joins that same batch, and the link does not move.
7. The user works down the grid at one click per card.
8. Afterwards the whole pass is one reviewable batch at `/batches/{id}` — named for the
   set, badged **Binder** — which is what makes an optimistic add safe: if client and
   server ever drift, the pass is auditable rather than an untracked run of writes.

### Flow 3: Inspect a pocket, and step its copies

1. User clicks a card's art (not a pip, not a badge).
2. The shared card modal opens with the large image, mana cost, type, mana value, set,
   collector number, rarity, condition, finish, treatment tags, SF/CK price links, and a
   "Full page →" link — then the binder's own block: foil-kind badges, the condition
   select, and one `−`/count/`+` row per finish.
3. `+` adds one copy of that finish, `−` removes one. Both are the same optimistic path a
   pip click takes: the count moves in the modal **and** on the tile behind it, the meters
   move if the pocket crossed between empty and filled, and the request follows. A `−`
   gives the copy's slot back to the visit's batch, so the review page's count stays equal
   to the copies still in the pass.
4. A double-faced card shows the flip button; clicking it turns the card over. The binder
   block re-renders with it and keeps its state, because it reads that state from the page
   rather than holding any.
5. Escape, the `×`, or a backdrop click dismisses the modal.

### Flow 3a: The condition sticks

1. User opens any card and sets the condition select to "Lightly Played".
2. Every add for the rest of the visit is filed under it — the modal's `+` on this card,
   the modal's `+` on the next card, **and every pip click in the grid**. The select is one
   page-scope variable, not per-card state.
3. This is the point of it: a physical binder is usually uniform, so re-picking the
   condition per card is the tax that makes a reconciliation pass not worth doing.
4. A reload is a new pass, and starts again at Near Mint.

### Flow 4: Narrow the view

1. User picks "Need" from the pocket filter → refetch; only empty pockets render.
2. User types in the in-set search → 250 ms after the last keystroke, refetch.
3. User toggles the "Promos" pill on → refetch; a Promos section appears below Extended.
4. **Through all of this the header meters do not move** — completion is computed before
   `q`, `filter` and `sections` are applied, so the numbers describe the set rather than
   the current view.

### Flow 5: Resize the grid

1. User clicks `+` / `−`. `--grid-cols` changes and the grid reflows immediately — no
   refetch, since the whole set is already in the page.
2. The count display updates; the buttons disable at 1 and 12.
3. The value is written to `localStorage` under `setsGridCols` **and** to the URL.

### Flow 6: Share or restore a view

1. Every control writes its state back to the query string, with defaults elided, via
   `history.replaceState` — so no control adds a history entry.
2. `/sets/fin?filter=need&sort=price&order=desc&cols=8` is a link; opening it restores
   that exact view before the first fetch.
3. `sections=base,extended` and `sort=number` never appear in the URL, because they are
   the defaults.

### Flow 7: A rejected add

1. User clicks a pip. The count increments optimistically and the tile repaints.
2. `POST /api/collection` returns non-2xx (or the network fails).
3. The increment is rolled back, the meters back out if they had moved, and a small
   uppercase red `.pip-error` note appears **on that tile** carrying the server's message
   (or "Network error"). Nothing page-wide changes; the rest of the binder pass is
   unaffected.
4. A step taken in the modal is rolled back the same way and also writes the message into
   the modal's `.binder-error` line, because the tile it happened to may well be behind the
   backdrop or off screen.

### Flow 8: An uncached or unknown set

1. User navigates to `/sets/zzz`.
2. `GET /api/set-browse/zzz` returns 404 with
   `"Set 'zzz' not cached (run `mtg cache all` to populate)"`.
3. Status turns red and shows the message; the content area shows the same message as an
   empty state. The header still reads "Loading…" as the set name, because the name only
   arrives with a successful response.

---

## 5. Dynamic Behavior

### `/sets` — on page load

- `loadSets()` calls `fetch('/api/sets/index')`. The response is unpaginated and already
  ordered newest-first, so the whole index arrives in one request.
- Rows are grouped into a `Map` keyed on `set_type`, then sorted by `SET_TYPE_RANK`.
- `set_type` is title-cased for display (`draft_innovation` → "Draft Innovation") rather
  than mapped through a hand-kept label table, because the types come straight from
  Scryfall and there are dozens of them.
- The rail and the sections are rendered from that one group array, so a rail row cannot
  name a section that is not on the page and their counts cannot drift apart. A type with
  no cached sets has no row, because it would jump nowhere; at prod scale all 24 ranked
  types are present.
- Each group carries its own tiles, its own search haystacks and its own owned flags,
  paired by position within the group. There is no page-wide running index over the tiles
  — that shape only held while every group contributed all of its tiles in document
  order, which is exactly what a collapsed or removed section breaks.

### `/sets` — collapsing

- `.open` on the `section.set-group` is the whole mechanism: `.set-grid` is
  `display: none` until then. Collapsing never removes a tile, so the filter still sees,
  hides and counts the tiles inside a collapsed group.
- Default-expanded is the first `DEFAULT_OPEN_RANKS` (4) entries of `SET_TYPE_RANK`:
  Expansion, Core, Commander, Masters — 211 of ~995 sets at prod scale. Reordering the
  rank moves the default with it; there is no second list. Deliberately *not*
  collapse-unless-owned: 13 of 24 MTG set types hold something, and that rule would
  default-expand Token and Promo, over half the catalogue.
- A rail row click expands its group and `scrollIntoView({behavior: 'smooth'})`s to it.
  A row whose group the filter emptied does nothing.
- The rail has no `overflow` of its own. If 24 rows stop fitting a laptop, the accepted
  fix is folding promo/token/memorabilia/minigame into one "Other products" row — not a
  scrollbar.

### `/sets` — filtering

- Search haystacks (`"{name} {code}"`, lowercased) are built once at wire-up, not per
  keystroke.
- Each `input` event runs one pass over the tiles: `tile.hidden` is set, the group's
  visible count and owned roll-up are recomputed, its rail row's count follows, a group
  with zero visible sets sets `hidden` on itself and dims its rail row, and
  `#sets-no-match` un-hides when nothing matched anywhere.
- While a filter is active it, not the user, decides what is open: a group with a match
  opens so the count and the page agree. Clearing the filter restores each group to
  whatever the user last chose, defaulting to the rank cutoff.
- No debounce and no network call — 993 sets at prod scale filter fast enough in the DOM.

### `/sets` — completion meters

- Two per tile: **"Set"** = `owned_base / total_base`, **"All"** = `owned_all / total_all`.
- A meter renders only when its total is `> 0`. `total_base` is null exactly when
  `sets.base_set_size` is — a permanent, legitimate state for a set no source reports a
  boundary for — and `null > 0` is false, so those sets show the All meter alone rather
  than a `0 / 0` bar reading NaN%.
- A meter at or above 100% gets `.complete` on its fill, which swaps the accent colour for
  the success colour.

### `/sets/:set_code` — view state

- `SET_CODE` is parsed from `location.pathname.split('/')[2]`, decoded and lowercased.
- `readUrl()` validates every parameter against its allowed set and falls back to the
  default rather than trusting the query string; `cols` additionally falls back to
  `localStorage.setsGridCols` before the hard default of 6, so cards-per-row is remembered
  across sets the way its four siblings are (`collectionGridCols`, `crackPackGridCols`,
  `exploreGridCols`, `recentGridCols`). **The URL wins when it says something.**
- `writeUrl()` serialises only the parameters that differ from `DEFAULTS`, with `sections`
  always in canonical `base,extended,promo` order.

### `/sets/:set_code` — loading

- Init order: `syncControls()` → `writeUrl()` → `fetch('/api/settings')` → `load()`.
  Settings are fetched **before** the first load, not fire-and-forget, because
  `price_sources` decides which price badges the tiles carry.
- `load()` requests `limit=1000` and renders everything it gets: a set is bounded — the
  largest real one is 779 printings — so there is no virtual scroller and no paging UI.
- Every control change calls `load()` again. There is no client-side re-sort; sorting,
  filtering and sectioning are all the server's answer.
- The status line normally just counts (`"599 printings"`). If the result ever exceeds the
  1000 cap it reads `"{total} printings, showing {N}"` rather than putting a short grid
  under a full count, which would read as a set with cards missing.

### `/sets/:set_code` — rendering

- Sections always render in `base` → `extended` → `promo` order regardless of the sort;
  the sort orders tiles *inside* a section, and the server has already applied it.
- A section with no rows is skipped entirely.
- Tiles come from `buildCardTile()` in `shared-card-tile.js` with `showQty`, `showBadges`
  and `showPips` on, and `packSetCode` set — so a printing from another set (a bonus sheet
  or reprint slot) gets the purple outer edge.
- The card object is stored on the element (`el._card`) so a repaint needs no lookup.

### `/sets/:set_code` — badges on a tile

Driven by the data present on the row, not by flags:
- **SF** link + optional TCG price — when `price_sources` includes `tcg`.
- **CK** link + optional CK price — when `price_sources` includes `ck` and `ck_url` exists.
- **Treatments**: `BL` (borderless), `SC` (showcase), `EA` (extended art), `FA` (full art).
- **Foil kind**: one badge per entry in `foil_kinds`, derived server-side from
  `promo_types` — "Surge", "Galaxy", "Ripple", "Textured", … Foil *kind* is a third axis,
  independent of whether the printing has a foil finish and of which finish a copy is in.
  Without it a surge-foil printing and its ordinary sibling look identical in the grid,
  which is precisely the reconciliation error the page exists to prevent.
- No pull-rate badge: binder rows carry no `pull_rate`.

### `/sets/:set_code` — optimistic stepping

- `changeCopies(card, finish, delta)` is the single path: `+1` from a pip click or the
  modal's `+`, `−1` from the modal's `−`. It moves the matching `owned` entry and
  `card.qty` locally, bumps the meters if the pocket crossed between empty and filled,
  repaints the tile and syncs the open modal — **then** issues the request.
- `+1` is `POST /api/collection` with
  `{printing_id, finish, condition, source: 'binder', batch}`.
- `−1` is two requests, because there is no "remove one copy of this printing" endpoint and
  should not be: a copy is a row with its own condition, price, order and history, so the
  copy to remove has to be named. `GET /api/collection/copies?printing_id&finish&status=owned`
  is ordered `acquired_at DESC`, so `copies[0]` is the copy the `+` just added; that id goes
  to `DELETE /api/collection/:id?confirm=true`. A mis-step undoes itself.
- `condition` is `_condition`, one page-scope variable set by the modal's select and read
  by every add of the visit, pips included. The endpoint 400s an unrecognised value rather
  than coercing it to Near Mint — a sticky select that silently downgraded would mislabel a
  whole binder rather than one copy.
- `repaintCard(card)` finds the tile by `data-printing-id` rather than taking an element,
  because a repaint replaces the node and the modal outlives several of them.
- `sessionBatch()` supplies that `batch`: `{batch_uuid, batch_type: 'binder_click', name:
  "{set name} binder", set_code}`. The uuid is minted on the **first add** and reused for
  the rest of the visit; the batch row is created server-side by the request that first
  carries it (`BatchRepository.get_or_create`) and joined by every later one. Browsing,
  filtering and paging post nothing, so they create no batch — the laziness is a
  consequence of that, not a rule enforced anywhere. `batch_uuid` is UNIQUE, so two
  clicks fast enough to race both end up in one batch rather than two.
- Optimistic on purpose: a binder pass is a run of adds, and waiting on each one is what
  makes the four-click `/collection` flow unusable for it.
- On failure the local state is reverted, the tile is repainted again, a `.pip-error` note
  is appended to it, and — when the step came from the modal — the message is also written
  into the modal's `.binder-error` line.
- `bumpCompletion()` moves the meters by one only on an empty→filled (or filled→empty)
  transition, and touches `owned_base` only for a `base`-section card. The meters count
  printings, never copies: a second copy of a card already held fills no new pocket.

### `/sets/:set_code` — click routing

One delegated listener on `#content`:
1. A click inside an `<a>` returns early (badges link out).
2. A click on `.finish-pip` adds a copy.
3. A click on `.sheet-card-img-wrap` opens the modal.

The pips are real `<button>`s rendered *outside* the clickable art rather than over it, so
"add one copy" and "open modal" never nest interactive elements. Click-to-add on the art
was considered and rejected — it makes the largest target on the page destructive-ish and
cannot say which finish it means.

Two more delegated listeners sit on the modal overlay, which is created once at page init
and outlives every card shown in it:

1. `change` on `#binder-condition` writes `_condition`.
2. `click` on `.binder-step` steps `_modalCard` by the button's `data-delta`.

`_modalCard` is *not* cleared when the modal closes — the shared modal has three ways to
close and announces none of them — so anything reading it also checks that the overlay
still carries `.active`.

---

## 6. Data Dependencies

### API endpoints called

| Endpoint | Method | Page | When | Returns |
|----------|--------|------|------|---------|
| `/api/sets/index` | GET | `/sets` | Page load | Bare JSON **array**, one object per cached set, newest release first |
| `/api/settings` | GET | `/sets/:set_code` | Page load, before the first grid fetch | `{key: value}` over the whole `settings` table; only `price_sources` is read |
| `/api/set-browse/:set_code` | GET | `/sets/:set_code` | Page load and every control change | Page envelope `{rows, total, limit, offset}` plus `set` and the four completion counts when `offset == 0` |
| `/api/collection` | POST | `/sets/:set_code` | A pip click, or the modal's `+` | `{id, batch_id}` for the created entry, or `{error}` with a non-2xx status. Body carries `condition`; an unrecognised one is a 400 |
| `/api/collection/copies` | GET | `/sets/:set_code` | The modal's `−`, to name the copy | A bare JSON **array** of copies, ordered `acquired_at DESC` |
| `/api/collection/:id?confirm=true` | DELETE | `/sets/:set_code` | The modal's `−`, once the copy is named | `{ok: true}`, or `{error}` with a non-2xx status |

### `/api/sets/index` row

```json
{
  "set_code": "fin",
  "set_name": "Final Fantasy",
  "set_type": "expansion",
  "released_at": "2025-06-13",
  "digital": 0,
  "base_set_size": 309,
  "total_set_size": 599,
  "owned_base": 118,
  "total_base": 311,
  "owned_all": 140,
  "total_all": 599
}
```

`owned_base` / `total_base` are **null** exactly when `base_set_size` is. `total_base` is
a count of printings at or below the boundary, not the boundary value — `fin` has
`base_set_size = 309` but 311 printings there, because suffixed numbers (`123a`, `123b`)
sit inside the base range.

### `/api/set-browse/:set_code` request parameters

| Param | Default | Accepted |
|-------|---------|----------|
| `limit` | 250 (the page always sends 1000) | 1 … `COLLECTION_LIMIT_MAX` (1000) |
| `offset` | 0 | ≥ 0 |
| `sort` | `number` | `number`, `name`, `rarity`, `price`, `qty` |
| `order` | `asc` | `asc`, `desc` |
| `filter` | `all` | `all`, `have`, `need` |
| `sections` | `base,extended` | comma-separated subset of `base`, `extended`, `promo` |
| `q` | *(none)* | free text; matched as `card.name LIKE %q%` |

Every unrecognised value is a **400 with an explanatory `{error}`**, never a silent clamp
or a fallback to the default — a view that quietly ignored `sort=collector` would hand back
a grid in the wrong order and look broken.

### `/api/set-browse/:set_code` response

Shape, with one illustrative row:

```json
{
  "rows": [
    {
      "printing_id": "…", "set_code": "fin", "collector_number": "6",
      "number_sortable": 600, "section": "base",
      "name": "Ambrosia Whiteheart", "rarity": "uncommon",
      "image_uri": "https://cards.scryfall.io/…", "layout": "normal",
      "mana_cost": "{2}{W}", "type_line": "Legendary Creature — …", "cmc": 3.0,
      "frame_effects": "[\"legendary\"]", "border_color": "black",
      "full_art": false, "promo": false,
      "finishes": ["nonfoil", "foil"],
      "foil_kinds": ["surgefoil"],
      "owned": [{"finish": "nonfoil", "qty": 2}, {"finish": "foil", "qty": 0}],
      "qty": 2,
      "wishlist_id": null, "wishlist_priority": null,
      "tcg_price": "0.35", "ck_price": "0.49",
      "ck_url": "https://www.cardkingdom.com/…"
    }
  ],
  "total": 599, "limit": 1000, "offset": 0,
  "set": {"set_code": "fin", "set_name": "Final Fantasy", "released_at": "2025-06-13",
          "base_set_size": 309, "total_set_size": 599},
  "owned_base": 118, "total_base": 311, "owned_all": 140, "total_all": 599
}
```

Contract points the page relies on:
- **One row per printing, never per copy.** `qty` is the total; `owned` breaks it down per
  finish and includes the finishes with zero copies, because that is the pip row the grid
  draws.
- `set` and the completion counts appear **only when `offset == 0`**, which is why the page
  guards `if (body.set)` before touching the header.
- Prices key on the *printing's* `finishes`, not on a held copy's finish — the pocket this
  view exists to show you is the one you have not filled, and it has no copy to take a
  finish from.

### Data that must exist

- At least one row in `sets` with `cards_fetched_at IS NOT NULL`, or `/sets` renders
  "No sets are cached yet — run: mtg cache all".
- The requested set must be cached, or the binder 404s. Nothing here falls back to Scryfall.
- `sets.base_set_size` decides the base/extended boundary. It is **stored, never derived**;
  NULL is permanent and legitimate for a set no source reports a size for, and both pages
  hide the base meter rather than render `0 / 0`.
- `printings.number_sortable` provides collector-number order and the base/extended split.
- `latest_prices` supplies `tcg_price` / `ck_price`; `mtgjson_printings` supplies `ck_url`.
  Missing prices render as a bare "SF" / "CK" badge, not an error.
- Card images come from the Scryfall CDN via `printings.image_uri` (external network), but
  every number on both pages is local.

---

## 7. Visual States

### `/sets`

| State | Appearance |
|-------|------------|
| **Loading** | Body is a single `.empty-state` with a spinner and "Loading sets…". `#sets-count` is blank |
| **Loaded** | A 220 px sticky `#sets-rail` and, beside it, one `.set-group` per set type — a heading with a caret, count and owned roll-up over a responsive `.set-grid` of `minmax(280px, 1fr)` tiles. `#sets-count` reads `"{N} sets"` |
| **Group collapsed** | Caret points right, `.set-grid` is `display: none`, tiles stay in the DOM. Everything below the top four ranked types starts here |
| **Group expanded** | Caret rotated 90°, grid shown |
| **Rail row** | Label left, count right, dimmed to 35% opacity when the filter left the group with nothing |
| **Narrow (≤700px)** | One column: the rail goes static above the grid and its rows wrap as bordered chips instead of standing 24 tall; tiles go one per row |
| **Tile** | Keyrune symbol at 2× on the left, spanning both text rows; set name (bold, ellipsised on overflow); sub-line `"{CODE} · {released_at}"`, or `"{CODE} · unreleased"` when `released_at` is null; then the meters across the full tile width |
| **Meter** | 3.2rem label ("Set" / "All"), a 6 px bar filled to the rounded percentage in the accent colour, and a tabular `"{owned} / {total}"` |
| **Meter complete** | Fill switches from accent to the success colour at 100% |
| **No base size** | The "Set" meter is absent entirely; only "All" renders |
| **Filtering** | Non-matching tiles and emptied groups get `hidden`; group counts show the visible number; `#sets-count` reads `"{shown} of {N} sets"` |
| **No match** | Every group hidden and `#sets-no-match` visible: "No set matches that filter." |
| **Nothing cached** | "No sets are cached yet — run: mtg cache all"; count reads "0 sets" |
| **Load error** | Body replaced by the server's `error` message, or `"Could not load sets (HTTP {status})"` |

### `/sets/:set_code`

| State | Appearance |
|-------|------------|
| **Initial** | Header reads "Loading…" with no set code; both meters hidden; controls already reflect the URL; content is a single "Loading…" empty state; status "Loading…" |
| **Loaded** | `<h1>` is the set name with the uppercased code beside it in grey; meters filled; one `.section` per non-empty section with a heading and `"{N} printings"`; status reads `"{total} printings"` |
| **Owned tile** | Full-colour art, gradient border (rarity at the top, `#111` or purple-for-off-set at the bottom), badges, filled pips in the rarity colour |
| **Owned, multiple copies** | A `qty-badge` reading `"{n}x"` over the art; the pip label carries its own per-finish count (`"Foil 3"`) |
| **Unowned tile** | `.unowned`: art at `grayscale(85%) brightness(0.55)`, opacity 0.6; the foil wash is suppressed — an unfilled pocket has no finish to be foil in; pips outlined, not filled |
| **Unowned + wishlisted** | `.unowned.wanted`: a softer dim (`grayscale(30%) brightness(0.75)`, opacity 0.85) plus a "Want" badge |
| **Foil printing owned in foil** | Rainbow gradient overlay plus the 3 s animated light streak from `shared-card-tile.css` |
| **Off-set printing** | Purple (`#5c2d91`) bottom edge instead of `#111` |
| **Pip hover** | Border and text lighten; the cursor is a pointer |
| **Pip failure** | A small uppercase red note under the pips carrying the server's message, or "Network error" |
| **No base size** | `#meter-base` carries `.hidden` and is not laid out; only "All printings" shows |
| **Section pill on** | Accent-filled button with white text; off is a dark button with grey text |
| **Sort direction** | "Asc" plain / "Desc" accent-filled |
| **Column buttons at a bound** | `disabled`, 30% opacity, `not-allowed` cursor |
| **Empty result** | "No printings match this view." — reached by a `q` or `filter` that excludes everything, while the header meters still show the whole set |
| **Uncached set (404)** | Status turns accent-red with the message; content shows the same text as an empty state; header still reads "Loading…" |
| **Bad parameter (400)** | Same treatment, with the endpoint's explanation, e.g. "sort must be one of number, name, rarity, price, qty" |
| **Modal open** | `.card-modal-overlay.active` — dark full-viewport backdrop, large card image with a flip button, and a details column (type, mana value, set, number, rarity, condition, finish, treatment tags, SF/CK links, "Full page →"), then the binder block: foil-kind badges, the condition select, and one `−`/count/`+` row per finish |
| **Empty pocket in the modal** | Its count reads `0` and its `−` is `disabled` at 30% opacity; the `+` is always live |
| **Modal step failure** | `.binder-error` fills with the server's message in small uppercase accent-red under the finish rows, and the counts snap back |
