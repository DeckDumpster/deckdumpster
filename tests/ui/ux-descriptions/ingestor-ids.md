# Manual ID Entry Page UX Description

**URL:** `/ingestor-ids`
**Source:** `mtg_collector/static/ingest_ids.html`
**Title:** Manual ID Ingestion - MTG Collection

---

## 1. Page Purpose

The Manual ID Entry page allows users to add cards to their collection by specifying each card's rarity code, collector number, and set code. This is the most precise ingestion method -- users look at the physical card, read the identifying information printed on it, and enter it manually. Cards are first queued in an entry list, then resolved against the local Scryfall database to confirm identity, and finally committed to the collection. The page supports foil marking, condition selection, batch grouping, and optional deck/binder assignment.

---

## 2. Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| "<-- Home" | `<a href="/">` | Home page | Header, leftmost |
| "Manual ID Ingestion" | `<h1>` | N/A (current page title) | Header |

---

## 3. Interactive Elements

### Input Panel (left side)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Rarity dropdown | `#rarity-select` | `<select>` | Dropdown with options: C (Common), U (Uncommon), R (Rare), M (Mythic), P (Promo), L (Land), T (Token). Defaults to C. |
| Collector Number input | `#cn-input` | `<input type="text">` | Text field for collector number. Placeholder: "0001". Has CSS class `cn-input` (width: 80px). Pressing Enter moves focus to the Set input. |
| Set Code input | `#set-input` | `<input type="text">` | Text field for set code. Placeholder: "NEO". Has CSS class `set-input` (width: 70px). Pressing Enter triggers `addEntry()`. |
| Foil checkbox | `#foil-check` | `<input type="checkbox">` | Checkbox to mark the card as foil. Label styled in gold (#d4af37). |
| Add button | `#add-btn` | `<button class="btn-primary">` | Adds the current rarity/CN/set/foil combination to the entry list. Calls `addEntry()`. |
| Entry table | `#entry-table` | `<table class="entry-table">` | Displays queued entries with columns: Rarity, CN, Set, Foil, Remove. |
| Entry table body | `#entry-tbody` | `<tbody>` | Dynamically populated rows of queued entries. |
| Remove buttons | `.remove-btn[data-idx]` | `<button>` | Per-row remove button (x symbol) in the entry table. Calls `removeEntry(idx)`. Uses event delegation on `#entry-tbody`. |
| Card count display | `#card-count` | `<div>` | Shows "Cards: N" count of queued entries. |
| Condition dropdown | `#condition-select` | `<select>` | Options: Near Mint (default), Lightly Played, Moderately Played, Heavily Played, Damaged. |
| Batch name input | `#batch-name` | `<input type="text">` | Optional batch name. Placeholder: "e.g. Foundations Starter Collection". Full width. |
| Product type dropdown | `#product-type` | `<select>` | Optional product type. Options: (empty default "Product type..."), Starter Collection, Booster Box, Bundle, Precon, Singles, Other. |
| Batch set code input | `#batch-set-code` | `<input type="text">` | Optional set code for the batch. Placeholder: "Set". Width: 70px. |
| Resolve button | `#resolve-btn` | `<button class="btn-primary">` | Sends queued entries to the API for resolution. Disabled when entry list is empty. |

### Result Panel (right side, dynamically rendered)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Assign target dropdown | `#assign-target` | `<select>` | Deck/binder assignment dropdown. First option: "No deck/binder assignment". Populated with optgroups for Decks and Binders after resolution. |
| Add to Collection button | `#commit-btn` | `<button class="btn-primary">` | Commits resolved cards to the collection. Shows spinner while processing. |
| Cancel button | `#cancel-btn` | `<button class="btn-secondary">` | Cancels the resolution, clears results, shows info message. |
| Foil toggles | `.foil-toggle[data-idx]` | `<span>` (clickable) | Per-card foil toggle in the resolved table. Shows "Foil" (gold, active) or "--" (gray, inactive). Clicking toggles the foil state. |
| Remove resolved buttons | `.remove-btn[data-resolved-idx]` | `<button>` | Per-card remove button in the resolved table. Removes a card from the resolved list. |
| Edit & Retry buttons | `.retry-btn[data-fail-idx]` | `<button class="btn-small">` | Per-card button in the failed section. Moves the failed entry back to the input list for editing. |

### Display Containers

| Element | ID | Description |
|---------|----|-------------|
| Entry list wrapper | `#entry-list-wrap` | Scrollable container for the entry table. |
| Results panel | `#results` | Right-side panel showing status messages, resolved cards table, and failed cards section. |

---

## 4. User Flows

### Flow 1: Add a Single Card Entry

1. User selects a rarity from the `#rarity-select` dropdown (defaults to C).
2. User types a collector number in `#cn-input` (e.g., "0001").
3. User types a set code in `#set-input` (e.g., "NEO").
4. Optionally checks the `#foil-check` checkbox.
5. User clicks "Add" or presses Enter while focused on the set input.
6. If both CN and set are non-empty, the entry is added to the `entries` array.
7. The entry table re-renders showing the new row.
8. The CN input is cleared and receives focus for rapid sequential entry.
9. The card count updates. The Resolve button becomes enabled.

### Flow 2: Keyboard-Driven Rapid Entry

1. User types collector number in `#cn-input`, presses Enter.
2. Focus moves to `#set-input`.
3. User types set code, presses Enter.
4. `addEntry()` fires: entry is added, CN input cleared and re-focused.
5. User immediately types the next collector number, repeating the cycle.
6. Rarity and foil persist between entries (only CN is cleared).

### Flow 3: Remove an Entry Before Resolving

1. User sees an entry in the table with incorrect data.
2. User clicks the red "x" remove button on that row.
3. `removeEntry(idx)` splices the entry from the array.
4. The table re-renders. Card count updates. If list becomes empty, Resolve button is disabled.

### Flow 4: Resolve Entries

1. User has one or more entries in the list.
2. User optionally sets the condition (defaults to Near Mint).
3. User optionally fills in batch name, product type, and batch set code.
4. User clicks "Resolve".
5. The Resolve button is disabled. The results panel shows "Resolving cards..." with a spinner.
6. `POST /api/ingest-ids/resolve` is called with `{ entries: [...] }`.
7. On success, the response contains `resolved` (array of matched cards) and `failed` (array of unmatched entries).
8. The results panel renders a summary bar, action bar, resolved table, and optionally a failed section.
9. The Resolve button re-enables.

### Flow 5: Review and Adjust Resolved Cards

1. After resolution, the resolved table shows each matched card with: thumbnail image, card name, set (code + full name), collector number, rarity, and foil status.
2. If a rarity mismatch occurred (user said R but card is U), a warning appears below the card name.
3. User can toggle foil on/off for any card by clicking the foil toggle.
4. User can remove a card from the resolved list by clicking its remove button.
5. User can select a deck or binder from the `#assign-target` dropdown.

### Flow 6: Handle Failed Resolutions

1. If some entries failed to resolve, a "Failed (N)" section appears below the resolved table.
2. Each failed entry shows: rarity, CN, set, and error message.
3. User can click "Edit & Retry" to move a failed entry back to the input list for correction.
4. The failed entry is removed from the failed list and added back to `entries`.
5. User can correct the entry and re-resolve.

### Flow 7: Commit Cards to Collection

1. User reviews the resolved cards and is satisfied.
2. User optionally selects a deck or binder assignment target.
3. User clicks "Add to Collection".
4. The button is disabled and shows a spinner with "Adding...".
5. `POST /api/ingest-ids/commit` is called with: `cards`, `condition`, `source: "manual_id"`, optional `assign_target`, optional `batch_name`, `product_type`, `batch_set_code`.
6. On success: a green success message shows "Added N card(s) to collection. M failed." The entry list and resolved/failed state are cleared.
7. On error: a red error message shows. The button re-enables with original text.

### Flow 8: Cancel After Resolution

1. User clicks "Cancel" in the action bar.
2. `resolvedCards` and `failedCards` are set to null.
3. The results panel shows an info message: "Cancelled. Add more cards to start over."
4. The entry list remains intact for re-use.

---

## 5. Dynamic Behavior

### On Page Load
- No API calls on load. The page starts with an empty entry list and an info message in the results panel: "Add cards using rarity, collector number, and set code, then click Resolve."

### Quick Add Input Handling
- CN input: Enter key moves focus to Set input (does not submit).
- Set input: Enter key calls `addEntry()` (submits the entry).
- After adding, CN input is cleared and re-focused for rapid sequential entry.
- The Add button also calls `addEntry()` on click.
- Validation: both CN and Set must be non-empty; if either is empty, `addEntry()` returns without action.

### Entry Table
- Rendered entirely client-side from the `entries` array.
- Remove buttons use event delegation on `#entry-tbody` (listening for `.remove-btn` clicks).
- Foil entries show a gold "Foil" tag; non-foil entries show nothing.

### Resolve Button State
- Disabled when `entries.length === 0`.
- Also disabled during resolution (re-enabled after response).

### Results Panel Rendering
- Fully replaced on each state change (innerHTML assignment).
- After rendering, event listeners are wired up for: commit button, cancel button, foil toggles, remove buttons, retry buttons.

### Assign Target Loading
- After successful resolution, `loadAssignTargets()` fetches both `/api/decks` and `/api/binders` in parallel.
- Decks are added as an optgroup labeled "Decks".
- Binders are added as an optgroup labeled "Binders".
- Each option value is formatted as `deck:ID` or `binder:ID`.

### Commit Button
- Shows a spinner animation inside the button while committing.
- On success, clears all state (entries, resolved, failed) and re-renders the entry table as empty.

### Rarity Mismatch Warning
- If the resolved card's actual rarity differs from what the user specified, a yellow italic warning appears: "Expected R, got U".

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When | Request Body | Response |
|----------|--------|------|-------------|----------|
| `/api/ingest-ids/resolve` | POST | Clicking "Resolve" | `{ entries: [{ rarity, collector_number, set_code, foil }, ...] }` | `{ resolved: [...], failed: [...] }` or `{ error: string }` |
| `/api/ingest-ids/commit` | POST | Clicking "Add to Collection" | `{ cards: [...], condition: string, source: "manual_id", assign_target?: string, batch_name?: string, product_type?: string, batch_set_code?: string }` | `{ added: int, failed: int }` |
| `/api/decks` | GET | After successful resolution | N/A | Array of deck objects with `id`, `name` |
| `/api/binders` | GET | After successful resolution | N/A | Array of binder objects with `id`, `name` |

### Data Prerequisites
- The local Scryfall card database must be populated (`mtg cache all`) for card resolution to work.
- Decks and/or binders must exist for the assignment feature to show options.

---

## 7. Visual States

### Input Panel States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Empty entry list** | `entries.length === 0` | Entry table shows only headers (Rarity, CN, Set, Foil). Card count shows "Cards: 0". Resolve button is disabled (grayed out). |
| **Entries queued** | `entries.length > 0` | Entry table populated with rows. Card count shows "Cards: N". Resolve button is enabled (red). |
| **Resolving in progress** | Resolve button clicked, awaiting response | Resolve button is disabled. |

### Results Panel States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Initial** | Page load, no action taken | Blue info message: "Add cards using rarity, collector number, and set code, then click Resolve." |
| **Resolving** | API call in progress | Blue info message with spinner animation: "Resolving cards..." |
| **Resolved (all success)** | All entries resolved | Summary bar showing "Resolved: N". Action bar with assign dropdown, "Add to Collection" button, and "Cancel" button. Resolved table with card thumbnails, names, sets, CNs, rarities, foil toggles, and remove buttons. |
| **Resolved (mixed)** | Some resolved, some failed | Same as above plus a "Failed (N)" section below with a red-bordered table of failed entries, each with error message and "Edit & Retry" button. |
| **Resolved (all failed)** | No entries resolved | Summary bar showing "Resolved: 0, Failed: N". Only the failed section is shown (no action bar or resolved table). |
| **API error** | Resolution API returns an error | Red error message with the error text. |
| **Committing** | Commit button clicked | Button shows spinner and "Adding..." text. Button is disabled. |
| **Commit success** | Commit completed | Green success message: "Added N card(s) to collection. M failed." |
| **Commit error** | Commit API fails | Red error message: "Commit failed: error text". Button re-enables. |
| **Cancelled** | Cancel button clicked | Blue info message: "Cancelled. Add more cards to start over." |

### Layout States

| Breakpoint | Behavior |
|------------|----------|
| Desktop (> 768px) | Two-panel layout: fixed-width input panel (450px) on left, flexible results panel on right. |
| Mobile (<= 768px) | Single-column layout: input panel stacks above results panel. Input panel takes full width. Entry list max-height is 150px. Resolved/failed tables use smaller font and padding. Card thumbnails shrink to 24x33px. |
