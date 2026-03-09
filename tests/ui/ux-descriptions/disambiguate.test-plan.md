# Disambiguate Page (`/disambiguate`) -- Test Plan

Source: `tests/ui/ux-descriptions/disambiguate.md`

## Existing Coverage

The following existing intent already covers a disambiguate page scenario:

- **`disambiguate_empty_state`** -- Verifies the empty state message appears when no cards are pending disambiguation, with a link to the Upload page. Covers Flow 5 and Visual State 1.

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### disambiguate_empty_state
- **Status**: EXISTING
- **Description**: When I navigate to the Disambiguate page with no cards pending disambiguation, I see an empty state message indicating there are no cards to disambiguate, with a link to the Upload page.
- **References**: UX Description S5 User Flows > Flow 5, S7 Visual States > State 1
- **Testability**: full
- **Priority**: high

### disambiguate_page_structure
- **Description**: When I navigate to the Disambiguate page with pending cards, I see the page header with the "Disambiguate" title linking to Home, navigation links (Home, Upload, Recent), a status summary showing the number of pending cards, and one card block per pending card containing a crop thumbnail, card metadata, action buttons, a search row, and a candidate grid.
- **References**: UX Description S1 Page Purpose, S2 Navigation, S3 Interactive Elements > Per-Card Block, S7 Visual States > State 2
- **Testability**: limited (requires ingest pipeline data with READY_FOR_DISAMBIGUATION status; test fixture may not include pending disambiguation cards without seeding the database with appropriate ingest_images records)
- **Priority**: high

### disambiguate_select_candidate
- **Description**: When I view a card block with multiple candidates, I can click on a candidate row to select it. The selected candidate gets a red border and darker background, all other candidates lose their selection, and the Confirm button becomes enabled. The finish dropdown auto-updates based on the selected candidate's foil status.
- **References**: UX Description S4 User Flows > Flow 1 (steps 5-6), S5 Dynamic Behavior > Candidate Grid Rendering, S7 Visual States > State 3 vs State 4
- **Testability**: limited (requires pending disambiguation data in the database)
- **Priority**: high

### disambiguate_confirm_card
- **Description**: After selecting a candidate, I click the Confirm button. The button text changes to "..." while the API call is in flight, and upon success the card block fades out and is removed. The status bar updates to show "Confirmed: 1" and the remaining card count decreases.
- **References**: UX Description S4 User Flows > Flow 1 (steps 8-10), S5 Dynamic Behavior > Card Confirmation, S7 Visual States > State 5, State 6
- **Testability**: limited (requires pending disambiguation data in the database)
- **Priority**: high

### disambiguate_confirm_all_done
- **Description**: When I confirm the last remaining card on the page, the empty state repurposes to show "All done!" with a count of confirmed cards and a "View Collection" link to /collection. The status summary also shows "All done! Confirmed N." and the status bar shows the final confirmed count.
- **References**: UX Description S4 User Flows > Flow 1 (step 11), S7 Visual States > State 10
- **Testability**: limited (requires pending disambiguation data in the database; ideally a single-card queue for simplicity)
- **Priority**: high

### disambiguate_manual_search
- **Description**: When I edit the search input field (pre-filled with the detected card name) and press Enter or click the Search button, the search button text changes to "..." while the API call runs. Upon completion the candidate grid replaces with the search results, the Confirm button is re-disabled, and any previous candidate selection is cleared.
- **References**: UX Description S4 User Flows > Flow 2, S5 Dynamic Behavior > Search, S7 Visual States > State 7
- **Testability**: limited (requires pending disambiguation data in the database)
- **Priority**: high

### disambiguate_show_all_candidates
- **Description**: When the narrowing algorithm filters the candidate list to fewer candidates than the full set, a "Show all N candidates" button appears below the grid. Clicking it replaces the narrowed grid with the full unfiltered candidate list and the button disappears.
- **References**: UX Description S4 User Flows > Flow 3, S5 Dynamic Behavior > Candidate Narrowing, S7 Visual States > State 9
- **Testability**: limited (requires pending disambiguation data where the narrowing algorithm produces a subset; depends on Claude OCR metadata matching some but not all candidates)
- **Priority**: medium

### disambiguate_photo_modal
- **Description**: When I click the cropped card thumbnail in a card block, a full-screen dark overlay (photo modal) appears showing the original uploaded photo at full resolution with a zoom-out cursor. Clicking anywhere on the modal dismisses it and returns to the normal page view.
- **References**: UX Description S4 User Flows > Flow 4, S5 Dynamic Behavior > Photo Modal, S7 Visual States > State 11
- **Testability**: limited (requires pending disambiguation data with an associated uploaded image)
- **Priority**: medium

### disambiguate_finish_dropdown
- **Description**: Each card block has a finish dropdown with three options: Nonfoil (default), Foil, and Etched. When I select a foil-only candidate, the dropdown auto-sets to "Foil". I can manually override the finish selection before confirming.
- **References**: UX Description S3 Interactive Elements > Finish selector, S4 User Flows > Flow 1 (steps 6-7)
- **Testability**: limited (requires pending disambiguation data with a foil-only candidate among the options)
- **Priority**: medium

### disambiguate_confirm_button_disabled_initial
- **Description**: When a card block first renders, the Confirm button is disabled (50% opacity, not clickable). It remains disabled until the user selects a candidate. After a search clears the selection, the Confirm button returns to the disabled state.
- **References**: UX Description S3 Interactive Elements > Confirm button, S7 Visual States > State 4
- **Testability**: limited (requires pending disambiguation data in the database)
- **Priority**: medium

### disambiguate_card_metadata_display
- **Description**: Each card block displays the OCR-detected metadata including the card name (as a heading), mana cost, type line (with subtype), rules text, power/toughness, set code, collector number, and artist. The source image filename is also shown below the metadata.
- **References**: UX Description S3 Interactive Elements > Per-Card Block, S5 Dynamic Behavior > On Page Load
- **Testability**: limited (requires pending disambiguation data with complete card_info metadata from Claude OCR)
- **Priority**: medium

### disambiguate_crop_thumbnail
- **Description**: Each card block shows a cropped thumbnail of the original uploaded photo, zoomed to the detected card region using CSS transforms. The thumbnail container has a zoom-in cursor indicating it is clickable.
- **References**: UX Description S3 Interactive Elements > Crop thumbnail, S5 Dynamic Behavior > Crop Thumbnail Rendering
- **Testability**: limited (requires pending disambiguation data with crop bounding box coordinates and an accessible uploaded image)
- **Priority**: low

### disambiguate_candidate_grid_layout
- **Description**: Candidates render in a grid layout with 10 columns on desktop. Each candidate shows a Keyrune set icon (with rarity-based color styling) and a card image. Hovering over a candidate row shows a tooltip with the card name, set name, and optional price.
- **References**: UX Description S5 Dynamic Behavior > Candidate Grid Rendering, S3 Interactive Elements > Candidate rows
- **Testability**: limited (requires pending disambiguation data; tooltip content requires specific price data)
- **Priority**: low

### disambiguate_no_candidates_found
- **Description**: When a search returns no matching candidates, the candidate area shows centered gray text reading "No candidates found" instead of a grid.
- **References**: UX Description S7 Visual States > State 8
- **Testability**: limited (requires pending disambiguation data and a search query that returns zero results)
- **Priority**: low

### disambiguate_navigation_links
- **Description**: The page header contains navigation links: the "Disambiguate" heading links to Home (/), plus dedicated links for "Home" (/), "Upload" (/upload), and "Recent" (/recent). Clicking each link navigates to the correct destination.
- **References**: UX Description S2 Navigation
- **Testability**: full (navigation links are present in the static HTML regardless of data state)
- **Priority**: low

### disambiguate_search_enter_key
- **Description**: When I type a card name in the search input field and press the Enter key, a search is triggered (equivalent to clicking the Search button). The search button shows "..." during the API call and the candidate grid updates with the results.
- **References**: UX Description S3 Interactive Elements > Search input, S4 User Flows > Flow 2 (step 3)
- **Testability**: limited (requires pending disambiguation data in the database)
- **Priority**: low

### disambiguate_status_bar_counter
- **Description**: The status bar in the header right side shows "Confirmed: N" after each card is confirmed, incrementing with each successful confirmation. Before any confirmations, the status bar is empty.
- **References**: UX Description S3 Interactive Elements > Status bar, S5 Dynamic Behavior > Card Confirmation
- **Testability**: limited (requires pending disambiguation data and performing confirmations)
- **Priority**: low

### disambiguate_settings_image_display
- **Description**: When the /api/settings endpoint returns image_display set to "contain", card images in the candidate grid use object-fit: contain (showing the full card without cropping) instead of the default cover mode.
- **References**: UX Description S5 Dynamic Behavior > On Page Load (Settings fetch), S7 Visual States > State 12
- **Testability**: limited (requires both pending disambiguation data and the image_display setting set to "contain")
- **Priority**: low

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| S1 Page Purpose | `disambiguate_page_structure` |
| S2 Navigation | `disambiguate_page_structure`, `disambiguate_navigation_links` |
| S3 Per-Card Block > Crop thumbnail | `disambiguate_crop_thumbnail`, `disambiguate_photo_modal` |
| S3 Per-Card Block > Confirm button | `disambiguate_confirm_button_disabled_initial`, `disambiguate_confirm_card`, `disambiguate_select_candidate` |
| S3 Per-Card Block > Finish selector | `disambiguate_finish_dropdown` |
| S3 Per-Card Block > Search input | `disambiguate_manual_search`, `disambiguate_search_enter_key` |
| S3 Per-Card Block > Search button | `disambiguate_manual_search` |
| S3 Per-Card Block > Candidate rows | `disambiguate_select_candidate`, `disambiguate_candidate_grid_layout` |
| S3 Per-Card Block > Show all button | `disambiguate_show_all_candidates` |
| S3 Global Elements > Status bar | `disambiguate_status_bar_counter` |
| S3 Global Elements > Status summary | `disambiguate_page_structure`, `disambiguate_confirm_all_done` |
| S3 Global Elements > Empty state | `disambiguate_empty_state` (EXISTING), `disambiguate_confirm_all_done` |
| S3 Global Elements > Dynamic settings style | `disambiguate_settings_image_display` |
| S4 Flow 1: Standard Disambiguation | `disambiguate_page_structure`, `disambiguate_select_candidate`, `disambiguate_confirm_card`, `disambiguate_confirm_all_done`, `disambiguate_finish_dropdown` |
| S4 Flow 2: Manual Search Override | `disambiguate_manual_search`, `disambiguate_search_enter_key` |
| S4 Flow 3: Expanding Narrowed Candidates | `disambiguate_show_all_candidates` |
| S4 Flow 4: Photo Zoom Modal | `disambiguate_photo_modal` |
| S4 Flow 5: Empty Queue | `disambiguate_empty_state` (EXISTING) |
| S5 On Page Load | `disambiguate_page_structure`, `disambiguate_settings_image_display` |
| S5 Candidate Narrowing | `disambiguate_show_all_candidates` |
| S5 Candidate Grid Rendering | `disambiguate_candidate_grid_layout`, `disambiguate_select_candidate` |
| S5 Card Confirmation | `disambiguate_confirm_card`, `disambiguate_confirm_all_done`, `disambiguate_status_bar_counter` |
| S5 Search | `disambiguate_manual_search`, `disambiguate_no_candidates_found` |
| S5 Crop Thumbnail Rendering | `disambiguate_crop_thumbnail` |
| S5 Photo Modal | `disambiguate_photo_modal` |
| S7 State 1: Empty Queue | `disambiguate_empty_state` (EXISTING) |
| S7 State 2: Cards Pending | `disambiguate_page_structure` |
| S7 State 3: Candidate Selected | `disambiguate_select_candidate` |
| S7 State 4: No Candidate Selected | `disambiguate_confirm_button_disabled_initial` |
| S7 State 5: Confirmation In Progress | `disambiguate_confirm_card` |
| S7 State 6: Card Resolved | `disambiguate_confirm_card` |
| S7 State 7: Search In Progress | `disambiguate_manual_search` |
| S7 State 8: No Candidates Found | `disambiguate_no_candidates_found` |
| S7 State 9: Narrowed vs Full | `disambiguate_show_all_candidates` |
| S7 State 10: All Done | `disambiguate_confirm_all_done` |
| S7 State 11: Photo Modal Open | `disambiguate_photo_modal` |
| S7 State 12: Settings-Modified Display | `disambiguate_settings_image_display` |

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 5 | `disambiguate_empty_state` (EXISTING), `disambiguate_page_structure`, `disambiguate_select_candidate`, `disambiguate_confirm_card`, `disambiguate_confirm_all_done`, `disambiguate_manual_search` |
| Medium | 5 | `disambiguate_show_all_candidates`, `disambiguate_photo_modal`, `disambiguate_finish_dropdown`, `disambiguate_confirm_button_disabled_initial`, `disambiguate_card_metadata_display` |
| Low | 7 | `disambiguate_crop_thumbnail`, `disambiguate_candidate_grid_layout`, `disambiguate_no_candidates_found`, `disambiguate_navigation_links`, `disambiguate_search_enter_key`, `disambiguate_status_bar_counter`, `disambiguate_settings_image_display` |

**Total new intents: 17** (plus 1 existing: `disambiguate_empty_state`)

## Testability Notes

Nearly all scenarios for the Disambiguate page are marked as **limited testability** because the page requires cards in the `READY_FOR_DISAMBIGUATION` state in the `ingest_images` table. This state is set by the ingest pipeline after Claude Vision OCR processing identifies multiple candidate printings for a card. The test fixture (`tests/fixtures/test-data.sqlite`) may not contain this data by default. Testing these scenarios requires either:

1. **Seeding the database** with appropriate `ingest_images` records (status = `READY_FOR_DISAMBIGUATION`, with valid `claude_result`, `scryfall_matches`, `crops`, and `disambiguated` JSON fields), or
2. **Running the full ingest pipeline** by uploading an image through `/upload` and processing it through OCR, which requires an `ANTHROPIC_API_KEY` and real image data.

The only exception is `disambiguate_navigation_links`, which can be tested with the empty-state page since the header links are present in the static HTML regardless of data state. The existing `disambiguate_empty_state` intent is also fully testable since it only validates the empty queue scenario.
