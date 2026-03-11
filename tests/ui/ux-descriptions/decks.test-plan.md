# Decks List Page (`/decks`) -- Test Plan

Source: `tests/ui/ux-descriptions/decks.md`

## Existing Coverage

The following existing intents already cover Decks List page scenarios:

- **`deck_list_links_to_standalone_detail`** -- Clicks a deck card on `/decks` and navigates to the standalone detail page at `/decks/:id`. Covers Flow 2 (Navigate to Deck Detail) and the deck card link behavior.
- **`deck_create_redirects_to_detail`** -- Creates a new deck from `/decks` via the "New Deck" modal, fills in name and format, saves, and confirms redirect to `/decks/:id`. Covers Flow 3 (Create a New Deck) including the redirect on success.
- **`decks_create_and_add_cards`** -- Creates a new deck with name and format, sees it in the list, opens it, and adds cards. Partially covers deck creation and the deck grid rendering.
- **`decks_precon_origin_metadata`** -- Creates a precon deck with Jumpstart origin metadata (checkbox, set, theme, variation). Covers Flow 4 (Toggle Precon Fields) and precon field visibility.
- **`decks_delete_keeps_cards`** -- Deletes a deck and verifies cards remain in the collection. Touches the deck list page but primarily tests collection behavior after deletion.

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### decks_list_page_structure
- **Filename**: `decks_list_page_structure`
- **Description**: When I visit `/decks`, I see a page with a legacy header showing "MTG / Decks" where "MTG" is a link back to the homepage. The header contains a "New Deck" button. Below the header, a grid of deck cards is displayed. Each card shows the deck name in the accent color, and the page uses the legacy header style (not the full site navigation bar with Collection, Decks, Binders, Sealed links).
- **Reference**: SS1 Page Purpose, SS2 Navigation, SS7 Visual States > State 2
- **Testability**: full
- **Priority**: high

### decks_list_empty_state
- **Filename**: `decks_list_empty_state`
- **Description**: When I visit `/decks` on an instance with no decks, I see an empty state message reading "No decks yet. Click 'New Deck' to create one." instead of a deck grid. The "New Deck" button is still visible in the header.
- **Reference**: SS4 User Flows > Flow 1 (step 4), SS7 Visual States > State 1
- **Testability**: limited (requires an instance with no decks; the test fixture includes demo decks, so decks would need to be deleted first)
- **Priority**: medium

### decks_list_card_content
- **Filename**: `decks_list_card_content`
- **Description**: When I visit `/decks` with existing decks, each deck card in the grid displays the deck name as a heading, a format badge (e.g. "commander" or "modern") in dark blue if a format is set, a purple "Precon" badge if the deck is a preconstructed deck, the storage location if provided, the description text if provided, the card count, and the total value if non-zero. All of these data points are visible on the card without clicking into it.
- **Reference**: SS5 Dynamic Behavior > Deck Grid Rendering, SS7 Visual States > State 2
- **Testability**: full
- **Priority**: high

### decks_list_card_links
- **Filename**: `decks_list_card_links`
- **Description**: When I visit `/decks`, each deck card in the grid is an anchor element (`<a>` tag) whose `href` points to `/decks/{id}`. I can verify this by inspecting the link target. Clicking the card performs standard browser link navigation to the standalone deck detail page rather than a JavaScript-driven view switch.
- **Reference**: SS2 Navigation (deck card element), SS4 User Flows > Flow 2, SS5 Dynamic Behavior > Deck Grid Rendering
- **Testability**: full
- **Priority**: high

### decks_list_responsive_grid
- **Filename**: `decks_list_responsive_grid`
- **Description**: When I visit `/decks` with multiple decks on a wide viewport, the deck cards are arranged in a responsive grid layout with auto-fill columns of minimum 280px width. On a narrow viewport (e.g. mobile width), the cards stack into a single column.
- **Reference**: SS7 Visual States > State 2 (responsive grid, min 280px)
- **Testability**: full
- **Priority**: medium

### decks_list_mtg_home_link
- **Filename**: `decks_list_mtg_home_link`
- **Description**: When I visit `/decks`, the header contains the text "MTG / Decks" where "MTG" is a clickable link. Clicking the "MTG" link navigates me back to the homepage at `/`.
- **Reference**: SS2 Navigation (MTG link in header)
- **Testability**: full
- **Priority**: medium

### decks_create_modal_opens
- **Filename**: `decks_create_modal_opens`
- **Description**: When I visit `/decks` and click the "New Deck" button, a modal opens with a dark backdrop overlay. The modal title reads "New Deck". I can see form fields for Name (with placeholder "My Commander Deck"), Format (dropdown with options including commander, standard, modern, pioneer, legacy, vintage, pauper), Description (textarea), a "Preconstructed deck" checkbox, Sleeve Color, Deck Box, and Storage Location. The precon-specific fields (Origin Set, Theme, Variation) are hidden. The modal has "Save" and "Cancel" buttons.
- **Reference**: SS3 Interactive Elements > Create/Edit Deck Modal, SS4 User Flows > Flow 3, SS7 Visual States > State 3
- **Testability**: full
- **Priority**: high

### decks_create_modal_precon_toggle
- **Filename**: `decks_create_modal_precon_toggle`
- **Description**: When I open the "New Deck" modal and check the "Preconstructed deck" checkbox, three additional fields appear: Origin Set dropdown (with options None, Jumpstart, Jumpstart 2022, Jumpstart 2025), Theme text input (placeholder "e.g. Goblins, Angels"), and Variation number input (1-4, placeholder "1-4"). When I uncheck the checkbox, these fields hide again.
- **Reference**: SS3 Interactive Elements > Create/Edit Deck Modal (precon fields), SS4 User Flows > Flow 4, SS7 Visual States > State 3 vs State 4
- **Testability**: full
- **Priority**: high

### decks_create_modal_validation
- **Filename**: `decks_create_modal_validation`
- **Description**: When I open the "New Deck" modal and click "Save" without entering a name, a browser alert appears with the message "Name is required". The modal remains open and any other data I entered (format, description, etc.) is preserved in the form fields.
- **Reference**: SS4 User Flows > Flow 3 (step 7 validation), SS7 Visual States > State 5
- **Testability**: full
- **Priority**: high

### decks_create_modal_cancel
- **Filename**: `decks_create_modal_cancel`
- **Description**: When I open the "New Deck" modal, fill in some form fields, and then click the "Cancel" button, the modal closes and I return to the deck list view. No new deck is created. The deck list remains unchanged.
- **Reference**: SS4 User Flows > Flow 3 (step 9), SS5 Dynamic Behavior > Modal System
- **Testability**: full
- **Priority**: medium

### decks_create_modal_backdrop_close
- **Filename**: `decks_create_modal_backdrop_close`
- **Description**: When I open the "New Deck" modal and click on the dark backdrop area outside the modal content, the modal closes without creating a deck. This verifies the backdrop click dismiss behavior.
- **Reference**: SS4 User Flows > Flow 5 (Close Modal via Backdrop Click), SS5 Dynamic Behavior > Modal System
- **Testability**: full
- **Priority**: medium

### decks_create_minimal
- **Filename**: `decks_create_minimal`
- **Description**: When I open the "New Deck" modal, enter only a name (the sole required field), and click "Save", the deck is created successfully. The browser redirects to the new deck's detail page at `/decks/:id`. The deck has no format, no description, and no precon metadata -- just the name I provided.
- **Reference**: SS4 User Flows > Flow 3, SS3 Interactive Elements > Create/Edit Deck Modal (only Name is required)
- **Testability**: full
- **Priority**: medium

### decks_create_full_fields
- **Filename**: `decks_create_full_fields`
- **Description**: When I open the "New Deck" modal and fill in every available field -- name, format (e.g. "modern"), description, sleeve color, deck box, and storage location -- and click "Save", the deck is created and I am redirected to its detail page. The detail page shows all the metadata I entered, confirming that every optional field was saved correctly.
- **Reference**: SS3 Interactive Elements > Create/Edit Deck Modal (all fields), SS4 User Flows > Flow 3
- **Testability**: full
- **Priority**: medium

### decks_list_card_hover_effect
- **Filename**: `decks_list_card_hover_effect`
- **Description**: When I hover over a deck card in the grid on `/decks`, the card's border color changes to the accent color and the background lightens slightly, providing visual feedback that the card is interactive and clickable.
- **Reference**: SS7 Visual States > State 2 (hover effect)
- **Testability**: full
- **Priority**: low

### decks_list_no_loading_indicator
- **Filename**: `decks_list_no_loading_indicator`
- **Description**: When I navigate to `/decks`, the page loads the deck list from the API without displaying any loading spinner or loading indicator. The deck grid simply appears once the data is fetched. This is the documented behavior -- no loading state is shown during the initial fetch.
- **Reference**: SS5 Dynamic Behavior > On Page Load, SS7 Visual States > State 6
- **Testability**: full
- **Priority**: low

### decks_list_format_badges
- **Filename**: `decks_list_format_badges`
- **Description**: When I visit `/decks` and decks exist with different formats assigned, each deck card displays its format as a dark blue badge (e.g. "commander", "modern", "standard"). Decks with no format set do not show a format badge. This confirms the conditional badge rendering.
- **Reference**: SS5 Dynamic Behavior > Deck Grid Rendering, SS7 Visual States > State 2
- **Testability**: full
- **Priority**: medium

### decks_list_precon_badge
- **Filename**: `decks_list_precon_badge`
- **Description**: When I visit `/decks` and a preconstructed deck exists, its card in the grid displays a purple "Precon" badge in addition to any format badge. Non-precon decks do not have this badge. This confirms that the precon status is visually indicated in the list view.
- **Reference**: SS5 Dynamic Behavior > Deck Grid Rendering (precon badge), SS7 Visual States > State 2
- **Testability**: full
- **Priority**: medium

### decks_list_value_display
- **Filename**: `decks_list_value_display`
- **Description**: When I visit `/decks`, deck cards that have a non-zero total value display the value on the card. Decks with zero value (or no priced cards) do not show a value field. This confirms the conditional value rendering in the deck grid.
- **Reference**: SS5 Dynamic Behavior > Deck Grid Rendering (total value if non-zero), SS7 Visual States > State 2
- **Testability**: limited (requires decks with priced cards in the test fixture; demo data may or may not include price data)
- **Priority**: low

### decks_list_storage_location_display
- **Filename**: `decks_list_storage_location_display`
- **Description**: When I visit `/decks`, deck cards that have a storage location set display that location text on the card. Decks without a storage location do not show this field. This confirms optional metadata rendering.
- **Reference**: SS5 Dynamic Behavior > Deck Grid Rendering (storage location), SS7 Visual States > State 2
- **Testability**: full
- **Priority**: low

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| SS1 Page Purpose | `decks_list_page_structure` |
| SS2 Navigation > MTG home link | `decks_list_mtg_home_link` |
| SS2 Navigation > Deck card links | `decks_list_card_links`, `deck_list_links_to_standalone_detail` (existing) |
| SS2 Navigation > Legacy header (no site nav bar) | `decks_list_page_structure` |
| SS3 Header Controls > New Deck button | `decks_create_modal_opens`, `deck_create_redirects_to_detail` (existing) |
| SS3 Create/Edit Deck Modal > All fields | `decks_create_modal_opens`, `decks_create_full_fields`, `decks_create_minimal` |
| SS3 Create/Edit Deck Modal > Precon fields | `decks_create_modal_precon_toggle`, `decks_precon_origin_metadata` (existing) |
| SS3 Create/Edit Deck Modal > Save/Cancel buttons | `decks_create_modal_validation`, `decks_create_modal_cancel` |
| SS4 Flow 1: View Deck List | `decks_list_page_structure`, `decks_list_card_content` |
| SS4 Flow 2: Navigate to Deck Detail | `decks_list_card_links`, `deck_list_links_to_standalone_detail` (existing) |
| SS4 Flow 3: Create a New Deck | `decks_create_modal_opens`, `decks_create_modal_validation`, `decks_create_minimal`, `decks_create_full_fields`, `deck_create_redirects_to_detail` (existing) |
| SS4 Flow 4: Toggle Precon Fields | `decks_create_modal_precon_toggle`, `decks_precon_origin_metadata` (existing) |
| SS4 Flow 5: Close Modal via Backdrop | `decks_create_modal_backdrop_close` |
| SS5 Dynamic Behavior > On Page Load | `decks_list_page_structure`, `decks_list_no_loading_indicator` |
| SS5 Dynamic Behavior > Deck Grid Rendering | `decks_list_card_content`, `decks_list_format_badges`, `decks_list_precon_badge`, `decks_list_value_display`, `decks_list_storage_location_display` |
| SS5 Dynamic Behavior > Modal System | `decks_create_modal_opens`, `decks_create_modal_cancel`, `decks_create_modal_backdrop_close` |
| SS7 Visual State 1: Empty (no decks) | `decks_list_empty_state` |
| SS7 Visual State 2: Loaded (decks exist) | `decks_list_page_structure`, `decks_list_card_content`, `decks_list_responsive_grid`, `decks_list_card_hover_effect` |
| SS7 Visual State 3: Create Modal Open | `decks_create_modal_opens` |
| SS7 Visual State 4: Create Modal with Precon | `decks_create_modal_precon_toggle` |
| SS7 Visual State 5: Validation Error | `decks_create_modal_validation` |
| SS7 Visual State 6: Network Error / No Loading | `decks_list_no_loading_indicator` |

## Intentionally Not Covered

The following areas from the UX description are **not** covered by new intents because they relate to the **legacy inline detail view** (`#detail-view`, `#detail-controls`) which is no longer the primary navigation path. The standalone Deck Detail page (`/decks/:id`) has replaced this functionality, and those scenarios are covered by `deck_detail_*` intents:

- SS3 Header Controls (Detail View) -- Back to Decks, Add Cards, Remove Selected, Import Expected List buttons
- SS3 Add Cards Modal (`#add-cards-modal`) -- card picker search, zone dropdown, add selected
- SS3 Expected List Import Modal (`#expected-modal`) -- decklist textarea, import button
- SS3 Legacy Inline Detail View Elements -- deck name, meta grid, edit/delete buttons, zone tabs, card table, completeness section
- SS6 Data Dependencies > API endpoints used only by the legacy inline view (`GET /api/decks/:id/cards`, `POST /api/decks/:id/cards`, etc.)

These legacy inline features are tested indirectly through `decks_import_expected_and_completeness`, `decks_reassemble_unassigned_cards`, and the `deck_detail_*` intents which test the equivalent functionality on the standalone detail page.

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 5 | `decks_list_page_structure`, `decks_list_card_content`, `decks_list_card_links`, `decks_create_modal_opens`, `decks_create_modal_precon_toggle`, `decks_create_modal_validation` |
| Medium | 8 | `decks_list_empty_state`, `decks_list_responsive_grid`, `decks_list_mtg_home_link`, `decks_create_modal_cancel`, `decks_create_modal_backdrop_close`, `decks_create_minimal`, `decks_create_full_fields`, `decks_list_format_badges`, `decks_list_precon_badge` |
| Low | 4 | `decks_list_card_hover_effect`, `decks_list_no_loading_indicator`, `decks_list_value_display`, `decks_list_storage_location_display` |

**Total new intents: 17** (plus 5 existing: `deck_list_links_to_standalone_detail`, `deck_create_redirects_to_detail`, `decks_create_and_add_cards`, `decks_precon_origin_metadata`, `decks_delete_keeps_cards`)
