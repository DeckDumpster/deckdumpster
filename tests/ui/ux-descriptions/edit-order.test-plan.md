# Edit Order Page — UI Scenario Test Plan

**Page:** `/edit-order?id=N`
**UX Description:** `tests/ui/ux-descriptions/edit-order.md`
**Date:** 2026-03-09

---

## Existing Coverage

| Intent file | What it covers |
|-------------|----------------|
| `edit_order_add_card.yaml` | Flow 4 (Add a New Card to the Order) — navigates from collection ordered view, searches, adds card, verifies it appears in the list. |

---

## Proposed Intents

### 1. edit_order_load_and_view

- **Filename:** `edit_order_load_and_view.yaml`
- **Description:** When I navigate to an order's edit page, I see the order metadata pre-filled in the left panel (seller name, order number, date, source, notes, and financial totals) and the card list in the right panel with a summary bar showing the card count and total value.
- **Reference:** Flow 1 (Load and View an Order), State 4 (Order Loaded with Cards), Section 3 (Order Metadata Panel, Cards Panel)
- **Testability:** full
- **Priority:** high

### 2. edit_order_no_id_error

- **Filename:** `edit_order_no_id_error.yaml`
- **Description:** When I navigate to `/edit-order` without an `?id=` parameter, the left panel shows an error message "No order ID specified. Use ?id=N" and the right panel is empty. No data loads.
- **Reference:** Flow 8 (Access Page Without Order ID), State 2 (No Order ID Error)
- **Testability:** full
- **Priority:** high

### 3. edit_order_save_metadata

- **Filename:** `edit_order_save_metadata.yaml`
- **Description:** On the edit order page, I modify the seller name and shipping cost, then click "Save Order Details". The button shows "Saving..." while the request is in flight, then a green "Saved" confirmation appears below the button and automatically disappears after a couple seconds.
- **Reference:** Flow 2 (Edit Order Metadata), State 6 (Save In Progress), State 7 (Save Success), Section 5 (Save Button State)
- **Testability:** full
- **Priority:** high

### 4. edit_order_inline_edit_card

- **Filename:** `edit_order_inline_edit_card.yaml`
- **Description:** On the edit order page, I change a card's condition dropdown to "Lightly Played", change its finish to "foil", and update its purchase price. Each change saves automatically on the change event without any visible save button or confirmation message.
- **Reference:** Flow 3 (Inline Edit a Card's Condition, Finish, or Price), Section 5 (Inline Card Updates)
- **Testability:** limited (no visual save feedback by design; can only verify the dropdowns/inputs accept new values and the page does not error)
- **Priority:** high

### 5. edit_order_remove_card

- **Filename:** `edit_order_remove_card.yaml`
- **Description:** On the edit order page, I click the remove button (X icon) on a card row, confirm the browser dialog, and the card disappears from the list. The summary bar updates to reflect the reduced card count and total value.
- **Reference:** Flow 6 (Remove a Card from the Order), State 14 (Remove Confirmation Dialog), Section 5 (Card List Refresh)
- **Testability:** limited (browser `confirm()` dialog is native and not rendered in the DOM; Playwright can intercept it but Claude Vision cannot see it)
- **Priority:** high

### 6. edit_order_replace_card

- **Filename:** `edit_order_replace_card.yaml`
- **Description:** On the edit order page, I click the replace button (arrows icon) on a card row, search for a different card in the overlay, select it, and the original card is replaced with the new one in the card list.
- **Reference:** Flow 5 (Replace a Card in the Order), Section 3 (Search Overlay)
- **Testability:** full
- **Priority:** high

### 7. edit_order_search_overlay_close

- **Filename:** `edit_order_search_overlay_close.yaml`
- **Description:** On the edit order page, I open the search overlay via the "+ Add Card" button, see the search input auto-focused with the placeholder "Search for a card...", then close the overlay by clicking the X button. No changes are made to the order. I then open it again and close it by clicking the dark backdrop area outside the modal.
- **Reference:** Flow 7 (Close Search Without Selecting), State 9 (Search Overlay Open Empty), Section 5 (Search Overlay)
- **Testability:** full
- **Priority:** medium

### 8. edit_order_search_no_results

- **Filename:** `edit_order_search_no_results.yaml`
- **Description:** On the edit order page, I open the search overlay and type a nonsensical query that matches no cards. After the debounce period, the results area shows "No results found" in gray text.
- **Reference:** State 12 (Search Overlay No Results), Section 5 (Search Overlay — minimum 2 characters, debounce)
- **Testability:** full
- **Priority:** medium

### 9. edit_order_card_row_elements

- **Filename:** `edit_order_card_row_elements.yaml`
- **Description:** On the edit order page with cards loaded, I verify that each card row displays a thumbnail image, the card name, set code and collector number, a condition dropdown, a finish dropdown, a price input, a replace button (arrows icon), and a remove button (X icon).
- **Reference:** State 4 (Order Loaded with Cards), Section 3 (Cards Panel per-card elements)
- **Testability:** full
- **Priority:** medium

### 10. edit_order_metadata_source_dropdown

- **Filename:** `edit_order_metadata_source_dropdown.yaml`
- **Description:** On the edit order page, I verify the Source dropdown contains the three expected options — "TCGPlayer", "Card Kingdom", and "Other" — and that the correct source is pre-selected based on the order data. I change the source to a different value and save.
- **Reference:** Section 3 (Order Metadata Panel — `#meta-source` select), Flow 2 (Edit Order Metadata)
- **Testability:** full
- **Priority:** medium

### 11. edit_order_empty_card_list

- **Filename:** `edit_order_empty_card_list.yaml`
- **Description:** When I navigate to an edit order page for an order that has no cards, the right panel shows "0 cards" and "Total value: $0.00" in the summary bar with the "+ Add Card" button, but no card rows are rendered.
- **Reference:** State 5 (Order Loaded with No Cards)
- **Testability:** limited (requires an order with zero cards in the test fixture; may need to remove all cards first)
- **Priority:** low

### 12. edit_order_navigation_home_link

- **Filename:** `edit_order_navigation_home_link.yaml`
- **Description:** On the edit order page, I see the "MTG Collection" header link styled in red. Clicking it navigates me back to the home page.
- **Reference:** Section 2 (Navigation), Section 3 (Header link)
- **Testability:** full
- **Priority:** low

### 13. edit_order_search_overlay_results_grid

- **Filename:** `edit_order_search_overlay_results_grid.yaml`
- **Description:** On the edit order page, I open the search overlay and type a card name. After the debounce, I see a "Searching..." spinner, then results appear as a grid of card tiles showing images, card names, and set/collector number info. Hovering over a result highlights it.
- **Reference:** State 10 (Search Overlay Searching), State 11 (Search Overlay Results Found), Section 5 (Search Overlay — grid layout, candidate display)
- **Testability:** full
- **Priority:** medium

---

## Coverage Matrix

| UX Description Section | Intents Covering It |
|------------------------|---------------------|
| Flow 1: Load and View | `edit_order_load_and_view` |
| Flow 2: Edit Metadata | `edit_order_save_metadata`, `edit_order_metadata_source_dropdown` |
| Flow 3: Inline Edit Card | `edit_order_inline_edit_card` |
| Flow 4: Add Card | `edit_order_add_card` (existing) |
| Flow 5: Replace Card | `edit_order_replace_card` |
| Flow 6: Remove Card | `edit_order_remove_card` |
| Flow 7: Close Search | `edit_order_search_overlay_close` |
| Flow 8: No Order ID | `edit_order_no_id_error` |
| State 2: No Order ID Error | `edit_order_no_id_error` |
| State 4: Loaded with Cards | `edit_order_load_and_view`, `edit_order_card_row_elements` |
| State 5: Loaded No Cards | `edit_order_empty_card_list` |
| State 6: Save In Progress | `edit_order_save_metadata` |
| State 7: Save Success | `edit_order_save_metadata` |
| State 9: Search Empty | `edit_order_search_overlay_close` |
| State 10: Searching | `edit_order_search_overlay_results_grid` |
| State 11: Results Found | `edit_order_search_overlay_results_grid`, `edit_order_add_card` (existing) |
| State 12: No Results | `edit_order_search_no_results` |
| State 14: Remove Confirm | `edit_order_remove_card` |
| Navigation | `edit_order_navigation_home_link` |
| Card Row Elements | `edit_order_card_row_elements` |
| Card Images | `edit_order_card_row_elements`, `edit_order_load_and_view` |
| Summary Bar Updates | `edit_order_remove_card`, `edit_order_add_card` (existing) |

### Not Covered (by design)

| Section | Reason |
|---------|--------|
| State 1: Loading (spinners) | Transient state; spinners disappear within milliseconds in test containers. Not feasible to capture reliably. |
| State 3: Order Not Found | Requires navigating to a non-existent order ID. Easy to test but low value — standard error path. Could add if desired. |
| State 8: Save Error | Would require simulating a server-side failure. Not feasible without mocking infrastructure. |
| State 13: Search Error | Would require simulating a search API failure. Not feasible without mocking infrastructure. |
| Responsive Layout (mobile) | Vision-based tests run at desktop viewport. Would need explicit viewport resizing, which is a separate concern. |
| Inline edit silent errors | Errors are logged to console only (by design). No visual indicator to validate. |
