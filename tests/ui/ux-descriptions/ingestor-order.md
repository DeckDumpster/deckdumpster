# Order Import Page UX Description

**URL:** `/ingestor-order`
**Source:** `mtg_collector/static/ingest_order.html`
**Title:** Order Ingestion - MTG Collection

---

## 1. Page Purpose

The Order Import page allows users to import cards from online marketplace orders (TCGPlayer and Card Kingdom). Users can paste order confirmation text or upload HTML files from these platforms. The page automatically parses the order data (extracting seller info, card names, quantities, conditions, prices), resolves the cards against the local Scryfall database, and presents a review interface before committing the cards to the collection. Orders can be marked as "Ordered" (not yet received) or "Owned" (already in hand), and cards can be optionally assigned to a deck or binder.

---

## 2. Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| "<-- Home" | `<a href="/">` | Home page | Header, leftmost |
| "Order Ingestion" | `<h1>` | N/A (current page title) | Header |

---

## 3. Interactive Elements

### Input Panel (left side)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Order text textarea | `#order-text` | `<textarea>` | Large text area for pasting order text. Placeholder: "Paste TCGPlayer/CK order text here...". Monospace font. Resizable vertically. Fills available panel height. |
| File upload drop zone | `#file-drop` | `<div class="file-upload">` | Dashed-border clickable area. Text: "Click or drop .html / .txt files". Supports drag-and-drop and click-to-browse. Changes border to green and shows filenames when files are loaded. |
| Hidden file input | `#file-input` | `<input type="file" multiple accept=".html,.htm,.txt">` | Hidden file input triggered by the drop zone. Accepts multiple HTML, HTM, and TXT files. |
| Format dropdown | `#format-select` | `<select>` | Order format selection. Options: Auto-detect (default), TCGPlayer HTML, TCGPlayer Text, Card Kingdom HTML, Card Kingdom Text. |
| Status pill: Ordered | `#status-pills .pill[data-value="ordered"]` | `<div>` (clickable) | Pill toggle for "Ordered" status. Active by default. Part of a pill row (segmented button group). |
| Status pill: Owned | `#status-pills .pill[data-value="owned"]` | `<div>` (clickable) | Pill toggle for "Owned" status. Clicking activates it and deactivates "Ordered". |
| Parse button | `#parse-btn` | `<button class="btn-primary">` | Initiates parsing and resolution of the order data. Text: "Parse". |

### Result Panel (right side, dynamically rendered)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Assign target dropdown | `#assign-target` | `<select>` | Deck/binder assignment dropdown. First option: "No deck/binder assignment". Populated with optgroups for Decks and Binders after resolution. |
| Add All to Collection button | `#commit-btn` | `<button class="btn-primary">` | Commits all resolved cards from all orders to the collection. Shows spinner while processing. |
| Cancel button | `#cancel-btn` | `<button class="btn-secondary">` | Cancels the import, clears resolved data, shows info message. |

### Display Containers

| Element | ID | Description |
|---------|----|-------------|
| Results panel | `#results` | Right-side panel showing status messages, order groups with item tables, and action controls. |

---

## 4. User Flows

### Flow 1: Paste Order Text and Parse

1. User pastes order confirmation text (from TCGPlayer or Card Kingdom) into the `#order-text` textarea.
2. User optionally selects a format from `#format-select` (Auto-detect usually works).
3. User selects the status: "Ordered" (cards not yet received) or "Owned" (cards in hand).
4. User clicks "Parse".
5. If textarea is empty, an error message appears: "No input provided."
6. The results panel shows "Parsing orders..." with a spinner. The Parse button is disabled.
7. `POST /api/order/parse` is called with the text and format.
8. If no orders found, an error appears: "No orders found in input."
9. If orders are found, a progress message shows: "Parsed N order(s), M items. Resolving cards..."
10. `POST /api/order/resolve` is called automatically with the parsed orders.
11. The resolved results render showing order groups with item tables.

### Flow 2: Upload HTML File(s) and Parse

1. User clicks the file drop zone or drags files onto it.
2. File picker opens (or files are dropped) -- accepts `.html`, `.htm`, `.txt` files. Multiple files allowed.
3. The drop zone text updates to show the filenames and border turns green.
4. File contents are read and concatenated into the `#order-text` textarea.
5. User proceeds with Parse as in Flow 1.

### Flow 3: Drag and Drop Files

1. User drags file(s) over the drop zone.
2. The drop zone border color changes to red (#e94560) on dragover.
3. User drops the files.
4. Border resets. File names appear in the drop zone text. Green border indicates files loaded.
5. File contents populate the textarea.

### Flow 4: Review Resolved Orders

1. After parsing and resolution, the results panel shows:
   - Summary bar: order count, resolved card count, failed card count (in red if any).
   - Action bar: assign target dropdown, "Add All to Collection" button, "Cancel" button.
   - One order group per order, each containing:
     - Order header: seller name, order number, order date, card count, total price.
     - Item table with columns: Card, Set, Condition, Qty, Price.
2. Resolved items show: card thumbnail, card name (with foil tag if applicable), set code + collector number, condition, quantity, and price.
3. Unresolved items have a red-tinted background and show an error message (e.g., "Not resolved") instead of full card data.

### Flow 5: Assign to Deck/Binder and Commit

1. User optionally selects a deck or binder from `#assign-target`.
2. User clicks "Add All to Collection".
3. The button is disabled and shows a spinner with "Adding...".
4. `POST /api/order/commit` is called with the resolved orders, selected status, and optional assignment target.
5. On success: a green success message shows "Added N card(s), linked M existing across O order(s). E error(s)."
6. If status was "Ordered", an additional guidance message appears (amber/gold styling): "Cards added as Ordered. When they arrive, go to Collection and filter by Ordered to mark them as received." This message includes a link to `/collection`.
7. On error: a red error message shows. The button re-enables.

### Flow 6: Cancel After Resolution

1. User clicks "Cancel" in the action bar.
2. `resolvedOrders` is set to null.
3. The results panel shows: "Cancelled. Paste new data to start over."

### Flow 7: Toggle Order Status

1. User clicks "Ordered" or "Owned" pill before parsing.
2. The clicked pill gets `.active` styling; the other loses it.
3. `selectedStatus` variable updates to the chosen value.
4. This status is sent with the commit request and determines whether cards are added as "ordered" or "owned" in the collection.

---

## 5. Dynamic Behavior

### On Page Load
- No API calls on load. The page starts with an empty textarea and an info message: "Paste order data or upload files, then click Parse."
- The "Ordered" status pill is active by default.

### File Upload Handling
- Drop zone click opens the hidden `#file-input` via `fileInput.click()`.
- Drag-and-drop is supported with visual feedback (border color change on dragover/dragleave/drop).
- Multiple files are accepted. All file contents are concatenated with newlines and placed in the textarea.
- The drop zone text updates to show comma-separated filenames.
- The drop zone gets `.has-files` class (green border).

### Two-Step Parse + Resolve
- Parsing and resolution happen in sequence within a single button click.
- First, `POST /api/order/parse` extracts order structure from the text.
- Then, `POST /api/order/resolve` matches card names to the local database.
- The user sees progressive status messages during this process.

### Status Pill Toggle
- Mutually exclusive: clicking one deactivates the other.
- Uses CSS `.active` class for styling (red background when active, dark background when inactive).
- State is stored in `selectedStatus` variable and sent with the commit.

### Assign Target Loading
- After resolution renders, `loadAssignTargets()` fetches `/api/decks` and `/api/binders` in parallel.
- Results populate the `#assign-target` dropdown with optgroups.
- Option values formatted as `deck:ID` or `binder:ID`.

### Order-Level Card Assignment
- The `assignCardsToTarget()` function exists in the code but is called from within `commitOrders()` implicitly -- the `assign_target` is sent with the commit payload.
- Direct assignment via `POST /api/decks/{id}/cards` or `POST /api/binders/{id}/cards` is also coded as a standalone function.

### Ordered vs Owned Guidance
- When committing with "Ordered" status, a special amber guidance message appears after success, directing users to the Collection page to mark cards as received when they arrive.

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When | Request Body | Response |
|----------|--------|------|-------------|----------|
| `/api/order/parse` | POST | Clicking "Parse" | `{ text: string, format: string }` | Array of parsed order objects, each with `seller_name`, `order_number`, `order_date`, `total`, `items: [{ parsed_name, set_hint, condition, quantity, price, foil }]` |
| `/api/order/resolve` | POST | Automatically after parse | `{ orders: [...parsedOrders] }` | Array of resolved order objects, same structure plus `resolved: bool`, `card_name`, `set_code`, `collector_number`, `image_uri`, `error` per item |
| `/api/order/commit` | POST | Clicking "Add All to Collection" | `{ orders: [...], status: string, source: "order_import", assign_target?: string }` | `{ cards_added: int, cards_linked: int, orders_created: int, errors: string[] }` |
| `/api/decks` | GET | After resolution renders | N/A | Array of deck objects with `id`, `name` |
| `/api/binders` | GET | After resolution renders | N/A | Array of binder objects with `id`, `name` |
| `/api/decks/{id}/cards` | POST | If assign target is a deck | `{ collection_ids: [...], zone: "mainboard" }` | N/A |
| `/api/binders/{id}/cards` | POST | If assign target is a binder | `{ collection_ids: [...] }` | N/A |

### Data Prerequisites
- The local Scryfall card database must be populated for card name resolution.
- Order text must be in a recognized format (TCGPlayer HTML/text, Card Kingdom HTML/text) for parsing to succeed.
- Decks and/or binders must exist for the assignment feature to show options.

---

## 7. Visual States

### Input Panel States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Empty** | No text or files | Empty textarea with placeholder. Drop zone shows "Click or drop .html / .txt files" with dashed border. |
| **Text pasted** | Textarea has content | Textarea shows the pasted text in monospace. |
| **Files loaded** | Files uploaded/dropped | Drop zone shows filenames with green border. Textarea populated with file contents. |
| **Parsing** | Parse button clicked | Parse button is disabled. |

### Results Panel States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Initial** | Page load | Blue info message: "Paste order data or upload files, then click Parse." |
| **No input error** | Parse clicked with empty textarea | Red error message: "No input provided." |
| **Parsing** | First API call in progress | Blue info with spinner: "Parsing orders..." |
| **No orders found** | Parse returned empty array | Red error message: "No orders found in input." |
| **Resolving** | Second API call in progress | Blue info with spinner: "Parsed N order(s), M items. Resolving cards..." |
| **Resolved (all items resolved)** | All items in all orders resolved | Summary bar (orders, resolved counts). Action bar. Order groups with green/normal item rows showing thumbnails, names, set info, condition, qty, price. |
| **Resolved (mixed)** | Some items unresolved | Same as above but unresolved rows have red-tinted background and show error tags instead of full card data. Summary bar shows failed count in red. |
| **Network/API error** | Fetch throws or API returns error | Red error message: "Error: [message]". |
| **Committing** | Commit button clicked | Button shows spinner and "Adding..." text. Button is disabled. |
| **Commit success (Owned)** | Commit completed with "Owned" status | Green success message with card/order counts. |
| **Commit success (Ordered)** | Commit completed with "Ordered" status | Green success message plus amber guidance message about marking cards as received, with link to Collection page. |
| **Commit error** | Commit API fails | Red error message: "Commit failed: [error]". Button re-enables with "Add All to Collection" text. |
| **Cancelled** | Cancel button clicked | Blue info message: "Cancelled. Paste new data to start over." |

### Layout States

| Breakpoint | Behavior |
|------------|----------|
| Desktop (> 768px) | Two-panel layout: 400px input panel on left, flexible results panel on right. Textarea fills available height. |
| Mobile (<= 768px) | Single-column layout: input panel stacks above results panel. Textarea constrained to 80-120px height. Item tables use smaller font and padding. Card thumbnails shrink to 24x33px. |
