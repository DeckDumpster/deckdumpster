# Homepage (`/`) -- index.html

## Page Purpose

The homepage serves as the central navigation hub for the MTG Collection Tools application. It presents all major features organized into three categorized groups (Collection, Analysis, Add Cards) and provides a settings panel for configuring application-wide preferences (image display mode and price sources). Each navigation link includes a short description of the destination page's purpose. The page also asynchronously displays a badge on the "Recent" link when there are cards currently being processed through the OCR ingest pipeline.

## Navigation

All navigation links are organized into three groups within a `.nav-row` flex container. Each group is a `.nav-group` inside a `.nav-col`.

### Collection Group

| Link Text | Href | Description |
|-----------|------|-------------|
| Cards | `/collection` | Browse with search, filters, and prices |
| Decks | `/decks` | Organize into decks with zones |
| Binders | `/binders` | Organize into binders |
| Sealed | `/sealed` | Track boxes, bundles, and sealed decks |
| Batches | `/batches` | View all import batches and orders |

### Analysis Group

| Link Text | Href | Description |
|-----------|------|-------------|
| Crack-a-Pack | `/crack` | Open virtual boosters with prices |
| Explore Sheets | `/sheets` | Booster structure and pull rates |
| Set Value | `/set-value` | Value distribution across sets |

### Add Cards Group

This group contains a nested OCR subgroup plus standalone ingestion links.

**OCR Subgroup** (inside `.nav-subgroup` with sub-label "OCR"):

| Link Text | Href | Description / Badge |
|-----------|------|---------------------|
| Upload | `/upload` | Badge wrapper: `#upload-badge-wrap` (currently unused) |
| Recent | `/recent` | Badge wrapper: `#recent-badge-wrap` (dynamically populated with processing count) |

**Other Add Cards Links:**

| Link Text | Href | Description |
|-----------|------|-------------|
| Corners | `/ingest-corners` | Photograph bottom-left corner text |
| Manual ID | `/ingestor-ids` | Enter rarity, collector number, set code |
| Orders | `/ingestor-order` | Import from TCGPlayer or Card Kingdom |
| CSV Import | `/import-csv` | Import from Moxfield, Archidekt, Deckbox |

### Other Links

- Favicon: `/static/favicon.ico` (in `<head>`)

There is no persistent header navigation bar, back link, or breadcrumb -- the homepage is the top-level entry point. Individual subpages must navigate back to `/` on their own.

## Interactive Elements

### Image Display Pills (Radio-style)

- **Container ID:** `image-display-pills`
- **Container class:** `pill-row`
- **Behavior:** Radio-style (mutually exclusive) -- clicking one deactivates the other
- **Setting key:** `image_display`
- **Pills:**

| Element | `data-value` | Label | Description |
|---------|-------------|-------|-------------|
| `.pill` | `crop` | Crop | Crops card images to fill their container |
| `.pill` | `contain` | Contain | Fits entire card image within the container |

When clicked:
1. All pills in the group have `.active` removed
2. The clicked pill gets `.active` added
3. `saveSetting('image_display', value)` is called

### Price Source Checks (Checkbox-style)

- **Container ID:** `price-source-checks`
- **Container class:** `check-row`
- **Behavior:** Checkbox-style (multi-select) -- each pill toggles independently
- **Setting key:** `price_sources`
- **Pills:**

| Element | `data-value` | Label | Description |
|---------|-------------|-------|-------------|
| `.pill` | `tcg` | TCG | TCGPlayer price data |
| `.pill` | `ck` | CK | Card Kingdom price data |

When clicked:
1. The clicked pill toggles its `.active` class
2. All currently active pill values are collected into a comma-separated string
3. `saveSetting('price_sources', joinedValues)` is called

### Save Status Indicator

- **Element ID:** `save-status`
- **Class:** `save-status`
- **Text content:** "Saved"
- **Behavior:** Hidden by default (`opacity: 0`). After any setting is saved, `.visible` is added (fades in), then removed after 1500ms (fades out).

### Navigation Links

All 13 navigation links (`<a>` elements inside `.nav-group`) are clickable and navigate to their respective pages. They have hover effects (border turns red `#e94560`, background lightens).

## User Flows

### Flow 1: Navigate to a Feature Page

1. User arrives at the homepage (`/`)
2. User scans the three navigation groups: Collection, Analysis, Add Cards
3. User reads the subtitle text under each link to understand the feature
4. User clicks a link (e.g., "Cards")
5. Browser navigates to the target page (e.g., `/collection`)

### Flow 2: Change Image Display Mode

1. User scrolls to the Settings section below the navigation grid
2. User sees the "Image Display" label with two pills: "Crop" and "Contain"
3. One pill is already highlighted (`.active`) based on the current saved setting
4. User clicks the inactive pill (e.g., switches from "Crop" to "Contain")
5. The clicked pill becomes active (red background), the other becomes inactive (dark background)
6. A PUT request is sent to `/api/settings` with `{"image_display": "contain"}`
7. The green "Saved" text fades in briefly (1.5 seconds), then fades out

### Flow 3: Toggle Price Sources

1. User scrolls to the Settings section
2. User sees the "Price Sources" label with two pills: "TCG" and "CK"
3. Zero, one, or both pills may be active based on current settings
4. User clicks a pill to toggle it:
   - If the pill was active, it becomes inactive (deselected)
   - If the pill was inactive, it becomes active (selected)
5. The current set of active values is joined with commas (e.g., `"tcg,ck"` or `"tcg"` or `""`)
6. A PUT request is sent to `/api/settings` with `{"price_sources": "tcg,ck"}`
7. The green "Saved" text fades in briefly, then fades out

### Flow 4: Check OCR Processing Status

1. User arrives at the homepage
2. The page asynchronously fetches `/api/ingest2/counts`
3. If there are cards with status `READY_FOR_OCR` or `PROCESSING`, the combined count appears as a red badge next to the "Recent" link with the text "processing"
4. User sees the badge and clicks "Recent" to view the processing queue
5. If there are no items processing, no badge is shown

## Dynamic Behavior

### On Page Load

Two asynchronous operations fire immediately when the page loads:

1. **`loadSettings()`** -- Fetches `GET /api/settings` and applies the response to the UI:
   - Sets the active pill in `#image-display-pills` based on `settings.image_display`
   - Sets active pills in `#price-source-checks` based on comma-separated `settings.price_sources`
   - Until this completes, no pills have the `.active` class (all appear inactive/gray)

2. **`loadIngestCounts()`** -- Fetches `GET /api/ingest2/counts` and conditionally injects a badge:
   - Sums `counts['READY_FOR_OCR']` and `counts['PROCESSING']`
   - If the total is greater than 0, injects HTML into `#recent-badge-wrap`:
     ```html
     <span class="badge">N</span> processing
     ```
   - If the total is 0 or the request fails (caught silently), no badge is shown
   - The `#upload-badge-wrap` span is present in the DOM but never populated by current code

### On Setting Change

When any pill is clicked:
1. The UI updates immediately (optimistic)
2. `saveSetting()` sends `PUT /api/settings` with `Content-Type: application/json`
3. On response, the `#save-status` element gets `.visible` class added
4. After 1500ms, `.visible` is removed (CSS transition handles fade)

### No Modals or Overlays

The homepage has no modals, dialogs, overlays, toasts (beyond the save status), or popups.

### No Polling or WebSocket

The page does not poll for updates or maintain any persistent connection. The ingest count and settings are fetched once on load.

## Data Dependencies

### API Endpoints Called

| Endpoint | Method | When | Request Body | Response |
|----------|--------|------|-------------|----------|
| `/api/settings` | GET | Page load | -- | JSON object with all settings (e.g., `{"image_display": "crop", "price_sources": "tcg,ck", ...}`) |
| `/api/settings` | PUT | On pill click | JSON with single key-value (e.g., `{"image_display": "contain"}`) | -- |
| `/api/ingest2/counts` | GET | Page load | -- | JSON object mapping ingest statuses to counts (e.g., `{"DONE": 2, "ERROR": 2, "READY_FOR_OCR": 0}`) |

### Required Data for Page to Function

- **Settings table** must exist in the database with at least the `image_display` and `price_sources` keys. Without it, `loadSettings()` would fail and no pills would be marked active, though the page would still render.
- **Ingest images table** must exist for the `/api/ingest2/counts` endpoint to respond. If the endpoint fails, the error is silently caught and no badge is shown -- the page still functions.
- The page itself is entirely static HTML with no server-side templating. All dynamic content is fetched via JavaScript after page load.

### No Authentication Required

The page and its API endpoints do not require authentication.

## Visual States

### State 1: Initial Load (Pre-JS)

- All navigation links are visible and styled
- Settings section is visible with "Image Display" and "Price Sources" labels
- All pills appear in their default (inactive) state -- dark background, gray text
- No badges are shown on any navigation links
- "Saved" text is invisible (opacity: 0)

### State 2: Fully Loaded (No Processing Items)

- Navigation links are rendered as before
- One Image Display pill has `.active` class (red background, white text) matching the saved setting
- Zero, one, or both Price Source pills have `.active` class matching the saved setting
- No badge appears on "Upload" or "Recent" links
- "Saved" text remains invisible

### State 3: Fully Loaded (With Processing Items)

- Same as State 2, except:
- The "Recent" link shows a red badge with the count of items being processed, plus the text "processing" after it (e.g., `<span class="badge">3</span> processing`)

### State 4: Setting Just Saved

- Same as State 2 or 3, except:
- The green "Saved" text is visible (`opacity: 1`) for 1.5 seconds before fading back out

### State 5: API Failure (Settings)

- If `GET /api/settings` fails, no pills are marked active
- The page is still fully navigable
- Clicking pills will still attempt to save (may also fail)

### State 6: API Failure (Ingest Counts)

- If `GET /api/ingest2/counts` fails, no badge is shown (error silently caught)
- The page is otherwise fully functional

### State 7: Mobile / Narrow Viewport (max-width: 768px)

- Body padding reduces from 32px to 20px
- `.nav-row` switches from horizontal flex to vertical column layout (`flex-direction: column`)
- Each `.nav-col` expands to full width (`width: 100%`)
- Navigation groups stack vertically instead of side-by-side
- Settings section remains unchanged (already max-width 320px)
