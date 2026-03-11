# Batches Page (`/batches`) -- Test Plan

Source: `tests/ui/ux-descriptions/batches.md`

## Existing Coverage

The following intents already cover batches-related scenarios:

- **`batches_homepage_nav_link`** -- Navigates from the homepage to the Batches page. Verifies the nav link exists and the page loads with batch names, card counts, and type badges.
- **`batches_type_filter_bar`** -- Filters batches by type using the pill buttons (Corner, All). Verifies active state toggles and list re-renders.
- **`batches_detail_view_and_metadata`** -- Clicks a batch to see detail view with name, type, date, card count, individual cards, and the Back button.
- **`corners_batch_browse`** -- Browses corner ingestion batches (from the corners page, not /batches). Shows date, card count, deck assignment, and card thumbnails.
- **`corners_batch_retroactive_deck_assign`** -- Assigns an unassigned corner batch to a deck (from the corners page). Verifies deck name appears in the list.
- **`csv_import_with_batch_metadata`** -- Verifies CSV import page shows optional batch metadata fields (batch name, product type, set code).

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### batches_page_header_and_navigation
- **Filename**: `batches_page_header_and_navigation`
- **Description**: When I navigate to `/batches`, I see a header with the title "Batches" and two navigation links: "Home" (linking to `/`) and "Collection" (linking to `/collection`). Clicking each link takes me to the correct page.
- **Reference**: Section 2 (Navigation)
- **Testability**: full
- **Priority**: high

### batches_list_view_populated
- **Filename**: `batches_list_view_populated`
- **Description**: When I visit the Batches page with existing batches in the database, the page loads a grid of batch cards. Each card displays the batch name (or "Batch #ID" if unnamed), a color-coded type badge, the creation date, and the card count. Batches with additional metadata show product type, set code, order number, or seller name.
- **Reference**: Section 4 Flow 1 (Browse All Batches), Section 7 Visual States (Populated)
- **Testability**: full
- **Priority**: high

### batches_empty_state
- **Filename**: `batches_empty_state`
- **Description**: When I visit the Batches page with no batches in the database, I see a centered empty-state message reading "No batches yet. Import cards via CSV, corners, or orders to create batches." instead of a grid.
- **Reference**: Section 7 Visual States (Empty - no batches)
- **Testability**: limited (requires a database with zero batches; the test fixture includes batches by default so this would need special fixture handling)
- **Priority**: medium

### batches_filter_each_type
- **Filename**: `batches_filter_each_type`
- **Description**: I can click each of the six filter pills (All, Corner, OCR, CSV Import, Manual ID, Orders) one at a time. Each click makes that pill active (red background) and deactivates the previously active pill. The batch grid re-renders to show only batches of the selected type. When I click "All", all batches reappear.
- **Reference**: Section 3 Interactive Elements (Filter pills), Section 4 Flow 2 (Filter Batches by Type), Section 5 Dynamic Behavior (Filter Interaction)
- **Testability**: full
- **Priority**: high

### batches_filter_empty_result
- **Filename**: `batches_filter_empty_result`
- **Description**: When I select a filter type that has no matching batches, the grid is replaced by the empty-state message. Switching back to "All" restores the full list.
- **Reference**: Section 7 Visual States (Filtered empty)
- **Testability**: full
- **Priority**: medium

### batches_detail_card_grid_with_images
- **Filename**: `batches_detail_card_grid_with_images`
- **Description**: When I click a batch that contains cards with image URIs, the detail view shows a card grid where each card displays its art image, card name, and set/collector number. The images use lazy loading.
- **Reference**: Section 4 Flow 3 (View Batch Details), Section 7 Visual States (Cards with images), Section 5 Dynamic Behavior (Card Images)
- **Testability**: full
- **Priority**: high

### batches_detail_card_fallback_image
- **Filename**: `batches_detail_card_fallback_image`
- **Description**: When I view a batch detail containing cards that lack an `image_uri`, those cards display the fallback card-back image (`/static/card_back.jpeg`) instead of a broken image icon.
- **Reference**: Section 5 Dynamic Behavior (Card Images), Section 7 Visual States (Cards without images)
- **Testability**: limited (requires batch cards with null image_uri in the fixture; demo data may always have image URIs populated)
- **Priority**: low

### batches_detail_info_section
- **Filename**: `batches_detail_info_section`
- **Description**: When I view a batch detail, I see an info section showing the batch type with its distinct color, and any available metadata: product type, set code, notes, and order information. Each field appears only when the data is present.
- **Reference**: Section 4 Flow 3 (View Batch Details), Section 5 Dynamic Behavior (Type Color Coding)
- **Testability**: full
- **Priority**: medium

### batches_assign_unassigned_to_deck
- **Filename**: `batches_assign_unassigned_to_deck`
- **Description**: When I view a batch that is not assigned to a deck, I see a deck dropdown (populated with existing decks), a zone dropdown (Mainboard/Sideboard/Commander defaulting to Mainboard), and an "Assign" button. I select a deck, leave the zone as Mainboard, and click "Assign". A green success message appears showing the number of cards assigned, and the dropdowns are replaced by a green "Assigned to: DeckName (mainboard)" status.
- **Reference**: Section 4 Flow 4 (Assign Batch to Deck), Section 7 Visual States (Unassigned batch, Assignment success)
- **Testability**: full
- **Priority**: high

### batches_assign_to_sideboard_zone
- **Filename**: `batches_assign_to_sideboard_zone`
- **Description**: When I assign an unassigned batch to a deck, I change the zone dropdown from Mainboard to Sideboard before clicking "Assign". After assignment, the status message shows the deck name with "(sideboard)" zone.
- **Reference**: Section 4 Flow 4 (Assign Batch to Deck), Section 3 Interactive Elements (Zone assignment dropdown)
- **Testability**: full
- **Priority**: medium

### batches_assign_no_deck_selected
- **Filename**: `batches_assign_no_deck_selected`
- **Description**: When I view an unassigned batch and click "Assign" without selecting a deck (the dropdown is still on "Select a deck..."), nothing happens -- no API call is made, no error message appears, and the form remains unchanged.
- **Reference**: Section 4 Flow 4 (Assign Batch to Deck), source code `assignDeck()` early return on empty deckId
- **Testability**: full
- **Priority**: medium

### batches_already_assigned_view
- **Filename**: `batches_already_assigned_view`
- **Description**: When I view a batch that is already assigned to a deck, I see a green "Assigned to: DeckName (zone)" status message instead of the deck/zone dropdowns and Assign button. No further assignment actions are available.
- **Reference**: Section 4 Flow 5 (View Already-Assigned Batch), Section 7 Visual States (Assigned batch)
- **Testability**: full
- **Priority**: high

### batches_detail_back_preserves_filter
- **Filename**: `batches_detail_back_preserves_filter`
- **Description**: I filter batches by a specific type, click into a batch detail, then click the "Back" button. The list view reappears and still shows the same filtered results with the same filter pill active, without a full page reload.
- **Reference**: Section 4 Flow 6 (Return to List from Detail), Section 5 Dynamic Behavior (Filter Interaction -- retained state)
- **Testability**: full
- **Priority**: high

### batches_type_color_coding
- **Filename**: `batches_type_color_coding`
- **Description**: I browse the batch list and verify that each batch type displays a distinctly colored badge: corner in red (#e94560), OCR in light blue (#88c0d0), CSV Import in green (#a3be8c), Manual ID in orange (#d08770), and Orders in purple (#b48ead). The badge uses the color for text and a lighter tinted background.
- **Reference**: Section 5 Dynamic Behavior (Type Color Coding)
- **Testability**: full
- **Priority**: medium

### batches_deck_label_in_list
- **Filename**: `batches_deck_label_in_list`
- **Description**: When a batch is assigned to a deck, its card in the batch list shows a green "Deck: DeckName" label. Unassigned batches do not show this label.
- **Reference**: Section 4 Flow 1 (Browse All Batches -- optional deck assignment), source code `renderList()` deckLabel
- **Testability**: full
- **Priority**: medium

### batches_assign_success_message_auto_dismiss
- **Filename**: `batches_assign_success_message_auto_dismiss`
- **Description**: After I successfully assign a batch to a deck, the green success message ("Assigned N card(s) to deck") appears in the detail view. After approximately 10 seconds, the message automatically disappears from the page.
- **Reference**: Section 5 Dynamic Behavior (Deck Assignment -- messages auto-dismiss after 10 seconds)
- **Testability**: limited (requires waiting 10 seconds for auto-dismiss; timing-dependent assertions may be flaky)
- **Priority**: low

### batches_assign_error_message
- **Filename**: `batches_assign_error_message`
- **Description**: When deck assignment fails (the API returns an error response), a red error message appears in the detail view showing the error text. The dropdowns and Assign button remain visible so I can retry.
- **Reference**: Section 4 Flow 4 (Assign Batch to Deck -- on error), Section 7 Visual States (Assignment error)
- **Testability**: limited (requires triggering an API error condition, such as assigning to a nonexistent deck or a batch that already has conflicting assignments)
- **Priority**: low

### batches_mobile_responsive_layout
- **Filename**: `batches_mobile_responsive_layout`
- **Description**: When I view the Batches page on a narrow viewport (768px or less), the batch grid collapses to a single column layout, and the card grid in the detail view uses smaller columns (min 100px instead of 140px).
- **Reference**: Section 7 Visual States (Responsive States)
- **Testability**: full
- **Priority**: medium

### batches_metadata_display_variants
- **Filename**: `batches_metadata_display_variants`
- **Description**: In the batch list, I can see how different batch types display their metadata: order-type batches show order number and seller name, CSV import batches show product type and set code, and batches without extra metadata show only the name, type badge, date, and card count.
- **Reference**: Section 4 Flow 1 (Browse All Batches -- optional metadata), Section 3 Interactive Elements (Batch cards)
- **Testability**: full
- **Priority**: medium

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| Page Purpose | `batches_list_view_populated`, `batches_page_header_and_navigation` |
| Navigation | `batches_page_header_and_navigation`, `batches_homepage_nav_link` (existing) |
| Interactive Elements > Filter pills | `batches_type_filter_bar` (existing), `batches_filter_each_type` |
| Interactive Elements > Batch cards | `batches_list_view_populated`, `batches_detail_view_and_metadata` (existing) |
| Interactive Elements > Back button | `batches_detail_view_and_metadata` (existing), `batches_detail_back_preserves_filter` |
| Interactive Elements > Deck dropdown | `batches_assign_unassigned_to_deck`, `batches_assign_no_deck_selected` |
| Interactive Elements > Zone dropdown | `batches_assign_unassigned_to_deck`, `batches_assign_to_sideboard_zone` |
| Interactive Elements > Assign button | `batches_assign_unassigned_to_deck`, `batches_assign_no_deck_selected` |
| Containers / Display Areas | `batches_list_view_populated`, `batches_detail_card_grid_with_images` |
| Flow 1: Browse All Batches | `batches_list_view_populated`, `batches_metadata_display_variants` |
| Flow 2: Filter Batches by Type | `batches_type_filter_bar` (existing), `batches_filter_each_type`, `batches_filter_empty_result` |
| Flow 3: View Batch Details | `batches_detail_view_and_metadata` (existing), `batches_detail_card_grid_with_images`, `batches_detail_info_section` |
| Flow 4: Assign Batch to Deck | `batches_assign_unassigned_to_deck`, `batches_assign_to_sideboard_zone`, `batches_assign_no_deck_selected`, `batches_assign_error_message` |
| Flow 5: View Already-Assigned Batch | `batches_already_assigned_view`, `batches_deck_label_in_list` |
| Flow 6: Return to List from Detail | `batches_detail_view_and_metadata` (existing), `batches_detail_back_preserves_filter` |
| Dynamic Behavior > On Page Load | `batches_list_view_populated` |
| Dynamic Behavior > Filter Interaction | `batches_type_filter_bar` (existing), `batches_filter_each_type`, `batches_filter_empty_result` |
| Dynamic Behavior > Batch Detail Loading | `batches_detail_view_and_metadata` (existing), `batches_detail_card_grid_with_images` |
| Dynamic Behavior > Deck Assignment | `batches_assign_unassigned_to_deck`, `batches_assign_success_message_auto_dismiss` |
| Dynamic Behavior > Card Images | `batches_detail_card_grid_with_images`, `batches_detail_card_fallback_image` |
| Dynamic Behavior > Type Color Coding | `batches_type_color_coding` |
| Visual States > Empty (no batches) | `batches_empty_state` |
| Visual States > Populated | `batches_list_view_populated` |
| Visual States > Filtered empty | `batches_filter_empty_result` |
| Visual States > Filtered populated | `batches_filter_each_type` |
| Visual States > Unassigned batch | `batches_assign_unassigned_to_deck` |
| Visual States > Assigned batch | `batches_already_assigned_view` |
| Visual States > Assignment success | `batches_assign_unassigned_to_deck`, `batches_assign_success_message_auto_dismiss` |
| Visual States > Assignment error | `batches_assign_error_message` |
| Visual States > Cards with images | `batches_detail_card_grid_with_images` |
| Visual States > Cards without images | `batches_detail_card_fallback_image` |
| Visual States > Responsive / Mobile | `batches_mobile_responsive_layout` |

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 6 | `batches_page_header_and_navigation`, `batches_list_view_populated`, `batches_filter_each_type`, `batches_detail_card_grid_with_images`, `batches_assign_unassigned_to_deck`, `batches_already_assigned_view`, `batches_detail_back_preserves_filter` |
| Medium | 8 | `batches_empty_state`, `batches_filter_empty_result`, `batches_detail_info_section`, `batches_assign_to_sideboard_zone`, `batches_assign_no_deck_selected`, `batches_type_color_coding`, `batches_deck_label_in_list`, `batches_mobile_responsive_layout`, `batches_metadata_display_variants` |
| Low | 4 | `batches_detail_card_fallback_image`, `batches_assign_success_message_auto_dismiss`, `batches_assign_error_message` |

**Total new intents: 18** (plus 3 existing: `batches_homepage_nav_link`, `batches_type_filter_bar`, `batches_detail_view_and_metadata`)
