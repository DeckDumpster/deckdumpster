# Card Detail Page (`/card/:set/:cn`) -- Test Plan

Source: `tests/ui/ux-descriptions/card-detail.md`

## Existing Coverage

The following intents already cover card detail scenarios:

- **`card_detail_direct_navigation`** -- Navigates directly to `/card/:set/:cn` and verifies the two-column layout: card image on the left, details panel on the right with name, mana cost, type line, set icon, collector number, rarity, artist, and external link badges.
- **`card_detail_from_collection_modal`** -- Navigates from the collection page modal "Full page" link to the standalone card detail page.
- **`card_detail_not_found`** -- Navigates to an invalid card URL and verifies the "Card not found" error message.
- **`card_detail_dfc_flip`** -- Flips a double-faced card and verifies the 3D animation and back-face metadata update.
- **`card_detail_want_toggle`** -- Toggles the Want/Wanted button and verifies text and styling changes.
- **`card_detail_add_copy`** -- Expands the add-to-collection form, fills in fields, confirms, and verifies a new copy appears.
- **`card_detail_delete_copy`** -- Deletes a copy via the Delete button with confirmation dialog.
- **`card_detail_dispose_copy`** -- Disposes of a copy (sold, traded, gifted, lost) with optional price and note.
- **`card_detail_receive_copy`** -- Receives an ordered copy and verifies status transition to owned.
- **`card_detail_deck_assign`** -- Assigns an unassigned copy to a deck and verifies the deck name and Remove link appear.
- **`card_detail_copy_history`** -- Expands and collapses the copy history timeline.
- **`card_detail_price_chart`** -- Verifies the price chart renders with range pills and that clicking a pill re-filters the chart.

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### card_detail_loading_state -- EXISTING: `card_detail_direct_navigation` (partial)
The loading spinner is implicitly validated by `card_detail_direct_navigation` (the page must load before content appears), but is not explicitly tested as a visible state.

---

### card_detail_metadata_display
- **Description**: When I navigate to a card's detail page, the details panel shows all expected metadata fields: card name, oracle name (if different from printed name), mana cost rendered as icons, type line, mana value, set name with keyrune icon and set code, collector number, rarity, artist name, and any treatment tags (e.g., extended art, showcase). Each field is present and correctly formatted.
- **References**: SS 4.1 View Card Details (step 7), SS 3 Interactive Elements > Action Buttons
- **Testability**: full
- **Priority**: high

### card_detail_external_links
- **Description**: On the card detail page, I can see "SF" and "CK" badges that link to Scryfall and Card Kingdom respectively. Each badge opens in a new tab. The Scryfall link follows the pattern `https://scryfall.com/card/:set/:cn`. The Card Kingdom link is generated via `getCkUrl()`. Both badges display price information when available.
- **References**: SS 2 Navigation (SF badge, CK badge), SS 4.1 View Card Details (step 7)
- **Testability**: full
- **Priority**: medium

### card_detail_site_header_nav
- **Description**: On the card detail page, the site header shows the "DeckDumpster" title linking to `/`, plus navigation links for "Collection", "Decks", "Binders", and "Sealed". Each link navigates to the correct destination.
- **References**: SS 2 Navigation (DeckDumpster, Collection, Decks, Binders, Sealed)
- **Testability**: full
- **Priority**: medium

### card_detail_page_title
- **Description**: When a card detail page loads successfully, the browser tab title updates to "{Card Name} -- DeckDumpster", reflecting the specific card being viewed.
- **References**: SS 4.1 View Card Details (step 6)
- **Testability**: full
- **Priority**: low

### card_detail_invalid_url_format
- **Description**: When I navigate to a URL that does not match the `/card/:set/:cn` pattern (e.g., `/card/` or `/card/fdn`), the page shows "Invalid card URL. Expected /card/:set/:cn" instead of card details.
- **References**: SS 7.2 Error State -- Invalid URL
- **Testability**: full
- **Priority**: medium

### card_detail_flip_non_dfc
- **Description**: When I view a non-double-faced card and click the flip button, the card image flips to show the generic card back image (`/static/card_back.jpeg`). The details panel does not change. Clicking again returns to the front face.
- **References**: SS 4.2 Flip Card Image (steps 5-6), SS 7.17 Card Flipped State
- **Testability**: full
- **Priority**: medium

### card_detail_add_form_toggle
- **Description**: On the card detail page, clicking the "Add" button opens the add-to-collection form. Clicking "Add" again while the form is open closes it without submitting. The form contains date (pre-filled with today), price, and source fields.
- **References**: SS 4.4 Add Card to Collection (step 9), SS 7.8 Add Form Expanded
- **Testability**: full
- **Priority**: medium

### card_detail_add_form_submitting_state
- **Description**: When I fill in the add-to-collection form and click "Confirm", the button text changes to "Adding..." and becomes disabled while the request is in flight. After success, the form closes and the new copy appears in the Copies section.
- **References**: SS 4.4 Add Card to Collection (steps 5-7), SS 7.9 Add Form -- Submitting
- **Testability**: full
- **Priority**: medium

### card_detail_copies_section_header
- **Description**: When I view a card detail page for a card I own copies of, a "Copies (N)" section header appears where N is the total number of copies. When I have no copies, no Copies section header appears.
- **References**: SS 4.5 View Owned Copies (steps 2-3), SS 7.4 Loaded State -- No Copies, SS 7.5 Loaded State -- With Copies
- **Testability**: full
- **Priority**: high

### card_detail_copy_card_fields
- **Description**: Each copy card in the Copies section displays the copy's finish, condition, source, acquisition date, and copy ID number. If applicable, it also shows order info (seller, order number, date), purchase price, and sale price.
- **References**: SS 4.5 View Owned Copies (steps 3-4)
- **Testability**: full
- **Priority**: high

### card_detail_dispose_listed_unlist
- **Description**: On the card detail page, when I have an owned copy I can select "Listed" from the disposition dropdown to mark it as listed. Once listed, the dropdown shows an "Unlist" option. Selecting "Unlist" returns the copy to owned status.
- **References**: SS 4.6 Dispose of a Copy, SS 3 Per-Copy Controls (dispose dropdown options)
- **Testability**: full
- **Priority**: medium

### card_detail_disposition_badges
- **Description**: After disposing of copies with different statuses (sold, traded, gifted, lost, listed), each copy displays the correct colored badge: sold in green, traded in yellow, gifted in blue, lost in red, listed in purple. The badge includes the disposition date and any note.
- **References**: SS 7.15 Disposition Badges (Inactive Copies)
- **Testability**: full
- **Priority**: medium

### card_detail_binder_assign
- **Description**: On the card detail page, an unassigned copy shows an "Add to Binder" dropdown listing all existing binders plus "New Binder...". Selecting a binder assigns the copy. After assignment, the copy shows the binder name with a "Remove" link and a "Move to Deck" dropdown.
- **References**: SS 4.9 Assign Copy to Deck or Binder (Unassigned copy, Copy in a binder)
- **Testability**: full
- **Priority**: high

### card_detail_move_deck_to_binder
- **Description**: On the card detail page, when a copy is assigned to a deck, I see the deck name, a red "Remove" link, and a "Move to Binder" dropdown. Selecting a binder from the dropdown atomically moves the copy from the deck to the binder.
- **References**: SS 4.9 Assign Copy to Deck or Binder (Copy in a deck)
- **Testability**: full
- **Priority**: medium

### card_detail_move_binder_to_deck
- **Description**: On the card detail page, when a copy is assigned to a binder, I see the binder name, a red "Remove" link, and a "Move to Deck" dropdown. Selecting a deck from the dropdown atomically moves the copy from the binder to the deck.
- **References**: SS 4.9 Assign Copy to Deck or Binder (Copy in a binder)
- **Testability**: full
- **Priority**: medium

### card_detail_remove_from_deck
- **Description**: On the card detail page, when a copy is assigned to a deck, I click the red "Remove" link next to the deck name. The copy becomes unassigned, and the "Add to Deck" and "Add to Binder" dropdowns reappear.
- **References**: SS 4.9 Assign Copy to Deck or Binder (Copy in a deck, step 2)
- **Testability**: full
- **Priority**: medium

### card_detail_remove_from_binder
- **Description**: On the card detail page, when a copy is assigned to a binder, I click the red "Remove" link next to the binder name. The copy becomes unassigned, and the "Add to Deck" and "Add to Binder" dropdowns reappear.
- **References**: SS 4.9 Assign Copy to Deck or Binder (Copy in a binder, step 2)
- **Testability**: full
- **Priority**: medium

### card_detail_new_deck_from_assign
- **Description**: On the card detail page, when assigning an unassigned copy to a deck, I select "New Deck..." from the dropdown. A prompt appears asking for a deck name. After entering a name, the new deck is created and the copy is assigned to it.
- **References**: SS 4.9 Assign Copy to Deck or Binder (Unassigned copy, step 3)
- **Testability**: limited (requires browser prompt interaction which Playwright supports but Claude Vision cannot directly validate the prompt dialog)
- **Priority**: medium

### card_detail_new_binder_from_assign
- **Description**: On the card detail page, when assigning an unassigned copy to a binder, I select "New Binder..." from the dropdown. A prompt appears asking for a binder name. After entering a name, the new binder is created and the copy is assigned to it.
- **References**: SS 4.9 Assign Copy to Deck or Binder (Unassigned copy, step 3)
- **Testability**: limited (requires browser prompt interaction which Playwright supports but Claude Vision cannot directly validate the prompt dialog)
- **Priority**: medium

### card_detail_copy_history_events
- **Description**: When I expand a copy's history timeline, I see chronological events with visual indicators: status events (e.g., "owned -> sold") have green dot indicators, and movement events (e.g., "Added to deck: My Deck") have blue dot indicators. Each event shows its date and optional note.
- **References**: SS 4.12 View Copy History (step 3), SS 7.10 Copy History Expanded
- **Testability**: full
- **Priority**: medium

### card_detail_copy_history_empty
- **Description**: When I expand the history for a newly added copy with no status changes or movements, the history section shows "No history" text.
- **References**: SS 7.12 Copy History -- Empty
- **Testability**: full
- **Priority**: low

### card_detail_price_chart_range_pills_disabled
- **Description**: On the card detail page price chart, range pills that exceed the available data span are visually dimmed and non-clickable (class `disabled`). The first non-disabled pill is automatically selected (class `active`).
- **References**: SS 4.13 Browse Price History (steps 4-5), SS 7.6 Loaded State -- Price Chart Visible
- **Testability**: full
- **Priority**: medium

### card_detail_price_chart_hidden_no_data
- **Description**: When I view a card detail page for a card with no price history data, the Price History section remains hidden (not visible in the DOM layout).
- **References**: SS 4.13 Browse Price History (step 2 condition), SS 7.7 Loaded State -- Price Chart Hidden
- **Testability**: full
- **Priority**: medium

### card_detail_price_chart_purchase_lines
- **Description**: When I view the price chart for a card that I own copies of with recorded purchase prices, dashed green horizontal lines appear on the chart at each purchase price level.
- **References**: SS 4.13 Browse Price History (step 7), SS 3 Price History Chart (chart canvas description)
- **Testability**: limited (Chart.js renders on canvas; visual validation of dashed lines requires pixel-level inspection or Claude Vision interpretation of the chart)
- **Priority**: low

### card_detail_mobile_layout
- **Description**: When I view the card detail page on a narrow viewport (below 768px), the layout switches from side-by-side columns to a stacked vertical layout. The card image section has reduced padding and the image width becomes viewport-relative instead of fixed height.
- **References**: SS 7.16 Responsive Layout (Mobile)
- **Testability**: full
- **Priority**: medium

### card_detail_wishlist_persists_on_load
- **Description**: When I navigate to a card detail page for a card already on my wishlist, the Want button initially loads in the "Wanted" state with green styling, without me needing to click it.
- **References**: SS 4.3 Add Card to Wishlist (steps 3-4), SS 7.18 Wishlist Active State, SS 5 Dynamic Behavior > Sequential after card loads
- **Testability**: full
- **Priority**: medium

### card_detail_delete_only_owned_ordered
- **Description**: On the card detail page, the Delete button only appears for copies with "owned" or "ordered" status. Copies that have been sold, traded, gifted, or lost do not show a Delete button.
- **References**: SS 3 Per-Copy Controls (delete button), SS 4.7 Delete a Copy (step 1)
- **Testability**: full
- **Priority**: medium

### card_detail_receive_button_only_ordered
- **Description**: On the card detail page, the green "Receive" button only appears for copies with "ordered" status. Owned, sold, traded, or other status copies do not show the Receive button.
- **References**: SS 3 Per-Copy Controls (receive button), SS 4.8 Receive an Ordered Copy (step 1)
- **Testability**: full
- **Priority**: medium

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| SS 1 Page Purpose | `card_detail_direct_navigation` (EXISTING), `card_detail_metadata_display` |
| SS 2 Navigation > Site header | `card_detail_site_header_nav` |
| SS 2 Navigation > SF badge | `card_detail_external_links` |
| SS 2 Navigation > CK badge | `card_detail_external_links` |
| SS 3 Card Image > Flip button | `card_detail_dfc_flip` (EXISTING), `card_detail_flip_non_dfc` |
| SS 3 Action Buttons > Want button | `card_detail_want_toggle` (EXISTING), `card_detail_wishlist_persists_on_load` |
| SS 3 Action Buttons > Add button | `card_detail_add_copy` (EXISTING), `card_detail_add_form_toggle`, `card_detail_add_form_submitting_state` |
| SS 3 Add-to-Collection Form | `card_detail_add_copy` (EXISTING), `card_detail_add_form_toggle`, `card_detail_add_form_submitting_state` |
| SS 3 Price History Chart | `card_detail_price_chart` (EXISTING), `card_detail_price_chart_range_pills_disabled`, `card_detail_price_chart_hidden_no_data`, `card_detail_price_chart_purchase_lines` |
| SS 3 Per-Copy Controls > Receive | `card_detail_receive_copy` (EXISTING), `card_detail_receive_button_only_ordered` |
| SS 3 Per-Copy Controls > Dispose | `card_detail_dispose_copy` (EXISTING), `card_detail_dispose_listed_unlist`, `card_detail_disposition_badges` |
| SS 3 Per-Copy Controls > Delete | `card_detail_delete_copy` (EXISTING), `card_detail_delete_only_owned_ordered` |
| SS 3 Per-Copy Controls > Reprocess | (not covered -- requires image lineage data, see Gaps below) |
| SS 3 Per-Copy Controls > Refinish | (not covered -- requires image lineage data, see Gaps below) |
| SS 3 Per-Copy Controls > Deck assignment | `card_detail_deck_assign` (EXISTING), `card_detail_new_deck_from_assign`, `card_detail_remove_from_deck`, `card_detail_move_deck_to_binder` |
| SS 3 Per-Copy Controls > Binder assignment | `card_detail_binder_assign`, `card_detail_new_binder_from_assign`, `card_detail_remove_from_binder`, `card_detail_move_binder_to_deck` |
| SS 3 Per-Copy Controls > History toggle | `card_detail_copy_history` (EXISTING), `card_detail_copy_history_events`, `card_detail_copy_history_empty` |
| SS 4.1 View Card Details | `card_detail_direct_navigation` (EXISTING), `card_detail_metadata_display`, `card_detail_page_title` |
| SS 4.2 Flip Card Image | `card_detail_dfc_flip` (EXISTING), `card_detail_flip_non_dfc` |
| SS 4.3 Add Card to Wishlist | `card_detail_want_toggle` (EXISTING), `card_detail_wishlist_persists_on_load` |
| SS 4.4 Add Card to Collection | `card_detail_add_copy` (EXISTING), `card_detail_add_form_toggle`, `card_detail_add_form_submitting_state` |
| SS 4.5 View Owned Copies | `card_detail_copies_section_header`, `card_detail_copy_card_fields` |
| SS 4.6 Dispose of a Copy | `card_detail_dispose_copy` (EXISTING), `card_detail_dispose_listed_unlist`, `card_detail_disposition_badges` |
| SS 4.7 Delete a Copy | `card_detail_delete_copy` (EXISTING), `card_detail_delete_only_owned_ordered` |
| SS 4.8 Receive an Ordered Copy | `card_detail_receive_copy` (EXISTING), `card_detail_receive_button_only_ordered` |
| SS 4.9 Assign to Deck/Binder | `card_detail_deck_assign` (EXISTING), `card_detail_binder_assign`, `card_detail_move_deck_to_binder`, `card_detail_move_binder_to_deck`, `card_detail_remove_from_deck`, `card_detail_remove_from_binder`, `card_detail_new_deck_from_assign`, `card_detail_new_binder_from_assign` |
| SS 4.10 Reprocess a Copy | (not covered -- see Gaps) |
| SS 4.11 Refinish a Copy | (not covered -- see Gaps) |
| SS 4.12 View Copy History | `card_detail_copy_history` (EXISTING), `card_detail_copy_history_events`, `card_detail_copy_history_empty` |
| SS 4.13 Browse Price History | `card_detail_price_chart` (EXISTING), `card_detail_price_chart_range_pills_disabled`, `card_detail_price_chart_hidden_no_data`, `card_detail_price_chart_purchase_lines` |
| SS 5 Dynamic Behavior > Initial Load | `card_detail_direct_navigation` (EXISTING) |
| SS 5 Dynamic Behavior > DOM Construction | `card_detail_direct_navigation` (EXISTING), `card_detail_metadata_display` |
| SS 5 Dynamic Behavior > Re-rendering | `card_detail_dfc_flip` (EXISTING), `card_detail_add_copy` (EXISTING), `card_detail_dispose_copy` (EXISTING) |
| SS 7.1 Loading State | `card_detail_direct_navigation` (EXISTING, partial) |
| SS 7.2 Error State -- Invalid URL | `card_detail_invalid_url_format` |
| SS 7.3 Error State -- Card Not Found | `card_detail_not_found` (EXISTING) |
| SS 7.4 Loaded State -- No Copies | `card_detail_copies_section_header` |
| SS 7.5 Loaded State -- With Copies | `card_detail_copies_section_header`, `card_detail_copy_card_fields` |
| SS 7.6 Price Chart Visible | `card_detail_price_chart` (EXISTING), `card_detail_price_chart_range_pills_disabled` |
| SS 7.7 Price Chart Hidden | `card_detail_price_chart_hidden_no_data` |
| SS 7.8 Add Form Expanded | `card_detail_add_form_toggle` |
| SS 7.9 Add Form -- Submitting | `card_detail_add_form_submitting_state` |
| SS 7.10 Copy History Expanded | `card_detail_copy_history` (EXISTING), `card_detail_copy_history_events` |
| SS 7.11 Copy History -- Loading | (not separately tested -- transient state) |
| SS 7.12 Copy History -- Empty | `card_detail_copy_history_empty` |
| SS 7.13 Copy History -- Error | (not covered -- requires API failure simulation) |
| SS 7.14 Copies -- Load Error | (not covered -- requires API failure simulation) |
| SS 7.15 Disposition Badges | `card_detail_disposition_badges` |
| SS 7.16 Mobile Layout | `card_detail_mobile_layout` |
| SS 7.17 Card Flipped State | `card_detail_dfc_flip` (EXISTING), `card_detail_flip_non_dfc` |
| SS 7.18 Wishlist Active State | `card_detail_want_toggle` (EXISTING), `card_detail_wishlist_persists_on_load` |

## Intentional Gaps

The following UX description sections are **not** covered by intents due to practical limitations:

| Section | Reason |
|---|---|
| SS 4.10 Reprocess a Copy | Requires copies with image lineage data (`ingest_lineage` records). The test fixture does not include OCR-ingested cards, so the Reprocess button never appears. Would require seeding the database with ingest pipeline artifacts. |
| SS 4.11 Refinish a Copy | Same as Reprocess -- requires image lineage data not present in the standard test fixture. |
| SS 7.11 Copy History -- Loading | Transient state that appears for milliseconds during API fetch. Not reliably capturable in a screenshot-based test. |
| SS 7.13 Copy History -- Error | Requires intercepting or failing the `/api/collection/:id/history` endpoint. Would need Playwright route interception beyond standard fixture capabilities. |
| SS 7.14 Copies -- Load Error | Requires intercepting or failing the `/api/collection/copies` endpoint. Same limitation as above. |

---

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 4 | `card_detail_metadata_display`, `card_detail_copies_section_header`, `card_detail_copy_card_fields`, `card_detail_binder_assign` |
| Medium | 21 | `card_detail_external_links`, `card_detail_site_header_nav`, `card_detail_invalid_url_format`, `card_detail_flip_non_dfc`, `card_detail_add_form_toggle`, `card_detail_add_form_submitting_state`, `card_detail_dispose_listed_unlist`, `card_detail_disposition_badges`, `card_detail_move_deck_to_binder`, `card_detail_move_binder_to_deck`, `card_detail_remove_from_deck`, `card_detail_remove_from_binder`, `card_detail_new_deck_from_assign`, `card_detail_new_binder_from_assign`, `card_detail_copy_history_events`, `card_detail_price_chart_range_pills_disabled`, `card_detail_price_chart_hidden_no_data`, `card_detail_mobile_layout`, `card_detail_wishlist_persists_on_load`, `card_detail_delete_only_owned_ordered`, `card_detail_receive_button_only_ordered` |
| Low | 3 | `card_detail_page_title`, `card_detail_copy_history_empty`, `card_detail_price_chart_purchase_lines` |

**Total existing intents: 12**
**Total new intents proposed: 28**
**Grand total: 40**
