# Collection Browser Page (`/collection`) -- Test Plan

Source: `tests/ui/ux-descriptions/collection.md`

## Existing Coverage

The following existing intents already cover Collection Browser page scenarios:

- **`collection_add_from_modal`** -- Adds a new copy of a card from the card detail modal by filling in purchase details and confirming. Covers Flow 4.8 (Adding a Card to Collection from Modal) and the inline add-collection form.
- **`collection_add_second_card_no_refresh`** -- Adds a card from the modal, closes it, opens a different card's modal, and adds that card too -- all without a full page refresh. Covers add-button resilience across consecutive modal opens.
- **`collection_card_modal_detail`** -- Opens a card modal from grid view and verifies card image, name, set, rarity, type line, and other metadata are displayed. Covers Flow 4.5 (Viewing Card Details) and modal visual structure.
- **`collection_deck_binder_filter`** -- Filters collection to show only unassigned cards using the container filter, then switches back. Covers Flow 4.20 (Container Filtering) and the container filter dropdown.
- **`collection_filter_rarity`** -- Opens the filter sidebar and selects rarity checkboxes to filter displayed cards, then clears filters. Covers Flow 4.3 (Filtering Collection) for the rarity dimension.
- **`collection_inline_deck_creation`** -- Creates a new deck inline from the card modal's Copies section via the "New Deck..." dropdown option. Covers Flow 4.7 (Managing Per-Copy Data) deck assignment with inline creation.
- **`collection_modal_close`** -- Opens a card modal from table view via the photo thumbnail and closes it using the X button. Covers Flow 4.5 modal open/close and the `modal-close` button.
- **`collection_multiselect_new_deck`** -- Multi-selects cards, clicks "Add to Deck", and creates a new deck inline from the assign modal. Covers Flow 4.10 (Multi-Select Operations) deck assignment with inline creation.
- **`collection_orders_view`** -- Switches to the orders view and verifies cards are grouped by order with visible card art thumbnails. Covers Flow 4.4 (Switching View Modes) orders variant and Section 3.12 (Orders View Elements).
- **`collection_price_chart`** -- Opens a card modal and verifies the Price History chart section with Chart.js line chart and time-range pills (1M, 3M, 6M, 1Y, ALL). Covers Section 3.6 (Price History Chart) and Section 5.5 (Card Modal Lazy Loading).
- **`collection_view_toggle`** -- Toggles between grid and table views using the view toggle buttons. Covers Flow 4.4 (Switching View Modes) for table and grid.
- **`views_container_only_filter`** -- Loads the "Unassigned Cards" saved view (container filter only, no search query) and verifies only unassigned cards appear. Covers Flow 4.18 (Saving and Loading Views) and the saved views dropdown.
- **`views_save_and_load`** -- Loads a saved view ("Modern Staples") from the sidebar and verifies the collection filters to the expected cards. Covers Flow 4.18 (Saving and Loading Views).

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### High Priority

#### collection_search_debounced
- **Filename**: `collection_search_debounced`
- **Description**: When I type a card name into the search input (`search-input`), the collection re-fetches from the server after a brief pause and displays only matching cards. Clearing the search input restores the full collection. The status text updates to reflect the filtered count.
- **UX Sections**: Flow 4.2 (Searching for a Card), Section 3.1 (Search input), Section 5.4 (Debouncing)
- **Testability**: full
- **Priority**: high

#### collection_filter_color
- **Filename**: `collection_filter_color`
- **Description**: When I open the filter sidebar and select one or more color pills (W, U, B, R, G, C), the collection view instantly re-renders to show only cards matching ALL selected colors (AND logic). Deselecting all color pills restores the full view.
- **UX Sections**: Flow 4.3 (Filtering Collection), Section 3.4 (Color Filter), Section 5.2 (Client-Side Filtering)
- **Testability**: full
- **Priority**: high

#### collection_filter_type
- **Filename**: `collection_filter_type`
- **Description**: When I open the filter sidebar and select a type filter pill (e.g., Creature, Instant), the collection re-renders to show only cards of that type. I can combine multiple type filters. The status text updates to reflect the filtered count.
- **UX Sections**: Flow 4.3 (Filtering Collection), Section 3.4 (Type Filter), Section 5.2 (Client-Side Filtering)
- **Testability**: full
- **Priority**: high

#### collection_sort_table_columns
- **Filename**: `collection_sort_table_columns`
- **Description**: In table view, I can click a column header (e.g., "Card", "Set", "Price") to sort the collection by that column. Clicking the same header again reverses the sort direction. An arrow indicator shows the current sort state.
- **UX Sections**: Flow 4.13 (Sorting), Section 3.10 (Table View Elements)
- **Testability**: full
- **Priority**: high

#### collection_modal_escape_close
- **Filename**: `collection_modal_escape_close`
- **Description**: When I open a card detail modal and press the Escape key, the modal closes and I return to the collection view. This tests an alternative close mechanism to the X button and backdrop click.
- **UX Sections**: Flow 4.5 step 9 (close via Escape), Section 3.6 (Card Detail Modal)
- **Testability**: full
- **Priority**: high

#### collection_modal_backdrop_close
- **Filename**: `collection_modal_backdrop_close`
- **Description**: When I open a card detail modal and click the semi-transparent backdrop area outside the modal content, the modal closes and I return to the collection view.
- **UX Sections**: Flow 4.5 step 9 (close via backdrop), Section 3.6 (`card-modal-overlay`)
- **Testability**: full
- **Priority**: high

#### collection_multiselect_toggle
- **Filename**: `collection_multiselect_toggle`
- **Description**: When I open the More menu and click "Toggle Multi-Select", the selection bar appears below the header with "0 selected" text, and checkboxes appear on each card. I can select individual cards and see the count update. Toggling multi-select off hides the bar and clears all selections.
- **UX Sections**: Flow 4.10 (Multi-Select Operations), Section 3.3 (Selection Bar), Section 7.7 (Selection Bar States)
- **Testability**: full
- **Priority**: high

#### collection_multiselect_delete
- **Filename**: `collection_multiselect_delete`
- **Description**: In multi-select mode, I select one or more cards and click the "Delete" button in the selection bar. A confirmation dialog appears showing the total quantity. After confirming, the selected cards are removed from the collection and the view updates.
- **UX Sections**: Flow 4.10 step 5 (Delete), Section 3.3 (`sel-delete-btn`)
- **Testability**: full
- **Priority**: high

#### collection_clear_filters
- **Filename**: `collection_clear_filters`
- **Description**: After applying multiple filters (e.g., rarity, color, set), I click "Clear Filters" at the bottom of the sidebar. All filters are reset, the search input is cleared, include-unowned is disabled, and the full collection re-loads.
- **UX Sections**: Section 3.4 (`clear-filters-btn`), Flow 4.3 step 6
- **Testability**: full
- **Priority**: high

#### collection_status_text_updates
- **Filename**: `collection_status_text_updates`
- **Description**: The status bar displays "N entries, N cards -- TCG $X.XX" reflecting the current filtered view. When I apply a filter that reduces the visible cards, the status text updates to show the new count and value. When I clear filters, it returns to the full count.
- **UX Sections**: Section 3.1 (`status`), Flow 4.1 step 3 (Basic Browsing)
- **Testability**: full
- **Priority**: high

### Medium Priority

#### collection_filter_set
- **Filename**: `collection_filter_set`
- **Description**: When I open the filter sidebar and type a set name into the set search input, a dropdown appears with matching sets. I select a set, and it appears as a removable pill. The collection re-renders to show only cards from that set. Removing the pill restores the full view.
- **UX Sections**: Section 3.4 (Set Filter), Flow 4.3 (Filtering Collection)
- **Testability**: full
- **Priority**: medium

#### collection_filter_finish
- **Filename**: `collection_filter_finish`
- **Description**: When I open the filter sidebar and select a finish pill (Nonfoil, Foil, or Etched), the collection instantly re-renders to show only cards with that finish. The foil shimmer effect is visible on foil cards in grid view.
- **UX Sections**: Section 3.4 (Finish Filter), Section 7.3 (Card Visual States -- foil/etched)
- **Testability**: full
- **Priority**: medium

#### collection_filter_treatment
- **Filename**: `collection_filter_treatment`
- **Description**: When I open the filter sidebar and select a treatment/badge filter pill (BL, SC, EA, FA, or Promo), the collection re-renders to show only cards matching that treatment. Treatment badges are visible on matching cards.
- **UX Sections**: Section 3.4 (Treatment Filter), Section 7.3 (Treatment badges)
- **Testability**: limited (requires cards with special treatments in the test fixture; demo data may not include borderless/showcase/extended art cards)
- **Priority**: medium

#### collection_filter_cmc_range
- **Filename**: `collection_filter_cmc_range`
- **Description**: When I open the filter sidebar and set a mana value range (CMC Min and CMC Max), the collection re-renders to show only cards within that mana cost range. Clearing the range inputs restores the full view.
- **UX Sections**: Section 3.4 (Mana Value Range), Section 5.4 (Debouncing -- 150ms)
- **Testability**: full
- **Priority**: medium

#### collection_filter_price_range
- **Filename**: `collection_filter_price_range`
- **Description**: When I open the filter sidebar and set a price range (Price Min and Price Max), the collection re-renders to show only cards within that price range. The status text updates to reflect the filtered value total.
- **UX Sections**: Section 3.4 (Price Range), Section 5.2 (Client-Side Filtering)
- **Testability**: limited (requires cards with price data in the test fixture)
- **Priority**: medium

#### collection_filter_date_range
- **Filename**: `collection_filter_date_range`
- **Description**: When I open the filter sidebar and set a date range (Date Min and Date Max), the collection re-renders to show only cards added within that date range.
- **UX Sections**: Section 3.4 (Date Added Range), Section 5.2 (Client-Side Filtering)
- **Testability**: full
- **Priority**: medium

#### collection_filter_subtype
- **Filename**: `collection_filter_subtype`
- **Description**: When I open the filter sidebar, type a subtype name (e.g., "Elf" or "Dragon") into the subtype search input, and select it from the dropdown, the collection re-renders to show only cards with that subtype. Selected subtypes appear as removable pills.
- **UX Sections**: Section 3.4 (Subtype Filter)
- **Testability**: full
- **Priority**: medium

#### collection_filter_cn_range
- **Filename**: `collection_filter_cn_range`
- **Description**: When I open the filter sidebar and set a collector number range (CN Min and CN Max), the collection re-renders to show only cards with collector numbers within that range.
- **UX Sections**: Section 3.4 (Collector Number Range), Section 5.2 (Client-Side Filtering)
- **Testability**: full
- **Priority**: medium

#### collection_column_config
- **Filename**: `collection_column_config`
- **Description**: In table view, I click the grid icon in the leftmost table header cell to open the column configuration drawer. I can toggle columns on and off (e.g., hide the Condition column, show the CK Buy $ column). The table re-renders immediately, and my choices persist across page reloads via localStorage.
- **UX Sections**: Flow 4.14 (Configuring Table Columns), Section 3.5 (Column Configuration Drawer)
- **Testability**: full
- **Priority**: medium

#### collection_grid_column_resize
- **Filename**: `collection_grid_column_resize`
- **Description**: In grid view, I see column count +/- controls in the header. Clicking "+" increases the number of columns (up to 12), and clicking "-" decreases them (min 1). The current count is displayed between the buttons, and the grid re-renders with the new column count.
- **UX Sections**: Flow 4.15 (Adjusting Grid Size), Section 3.1 (Grid column controls)
- **Testability**: full
- **Priority**: medium

#### collection_grid_sort_bar
- **Filename**: `collection_grid_sort_bar`
- **Description**: In grid view, a sort bar appears above the grid with sort buttons for each column (Qty, Card, Type, Cost, Set, #, Price, etc.). Clicking a sort button sorts the grid by that field, and clicking it again reverses the direction. An arrow indicator shows the active sort.
- **UX Sections**: Flow 4.13 (Sorting -- grid view), Section 3.11 (Grid View Elements -- sort bar)
- **Testability**: full
- **Priority**: medium

#### collection_modal_filterable_click
- **Filename**: `collection_modal_filterable_click`
- **Description**: When I open a card detail modal, clickable elements like the set name, rarity, and type line have a filterable styling. Clicking a filterable element (e.g., the set name) closes the modal and applies that value as a filter in the sidebar, re-rendering the collection to show only matching cards.
- **UX Sections**: Flow 4.6 (Clicking Filterable Elements in Modal), Section 5.10 (Filterable Element Click Propagation)
- **Testability**: full
- **Priority**: medium

#### collection_modal_full_page_link
- **Filename**: `collection_modal_full_page_link`
- **Description**: When I open a card detail modal, a "Full page" badge is visible that links to the standalone card detail page at `/card/:set/:cn`. Clicking it navigates to the standalone page.
- **UX Sections**: Section 2 (Navigation -- Modal "Full page" badge), Flow 4.5 step 5
- **Testability**: full
- **Priority**: medium

#### collection_modal_want_button
- **Filename**: `collection_modal_want_button`
- **Description**: When I open a card detail modal, I can click the "Want" button to add the card to my wishlist. The button changes to "Wanted" with green styling. Clicking again removes it from the wishlist and reverts the button.
- **UX Sections**: Section 3.6 (`modal-want-btn`), Flow 4.9 step 7 (Wishlist Management)
- **Testability**: full
- **Priority**: medium

#### collection_modal_copy_deck_assignment
- **Filename**: `collection_modal_copy_deck_assignment`
- **Description**: In the card detail modal, I can assign an unassigned copy to an existing deck using the "Add to Deck" dropdown in the copy section. After selecting a deck, the copy shows its deck assignment, and a "Remove from Deck" link appears.
- **UX Sections**: Flow 4.7 (Managing Per-Copy Data -- assign to deck), Section 3.6 (Per-Copy Sections)
- **Testability**: full
- **Priority**: medium

#### collection_modal_copy_binder_assignment
- **Filename**: `collection_modal_copy_binder_assignment`
- **Description**: In the card detail modal, I can assign an unassigned copy to an existing binder using the "Add to Binder" dropdown. After selecting a binder, the copy shows its binder assignment. I can then remove it via the "Remove from Binder" link.
- **UX Sections**: Flow 4.7 (Managing Per-Copy Data -- assign to binder), Section 3.6 (Per-Copy Sections)
- **Testability**: full
- **Priority**: medium

#### collection_modal_delete_copy
- **Filename**: `collection_modal_delete_copy`
- **Description**: In the card detail modal's Copies section, I click the delete button on a specific copy. A confirmation dialog appears. After confirming, the copy is removed and the copies section refreshes with one fewer entry.
- **UX Sections**: Flow 4.7 (Managing Per-Copy Data -- delete), Section 3.6 (`delete-copy-btn`)
- **Testability**: full
- **Priority**: medium

#### collection_modal_dfc_flip
- **Filename**: `collection_modal_dfc_flip`
- **Description**: When I open a card detail modal for a double-faced card, a circular flip button appears in the bottom-right of the image area. Clicking it rotates the card 180 degrees on the Y axis to show the back face. Clicking again returns to the front face.
- **UX Sections**: Flow 4.5 step 8 (Flip DFC), Section 3.6 (`modal-flip-btn`, `modal-flip`), Section 7.5 (Modal States -- Flipped)
- **Testability**: limited (requires a double-faced card in the test fixture)
- **Priority**: medium

#### collection_wishlist_panel
- **Filename**: `collection_wishlist_panel`
- **Description**: When I open the More menu and click "Wishlist (N)", the wishlist panel slides in from the right showing a list of wanted cards. I can click X on an entry to remove it. The panel shows the updated count. I can close the panel by clicking the backdrop or the X button.
- **UX Sections**: Flow 4.9 (Wishlist Management), Section 3.7 (Wishlist Panel), Section 7.6 (Wishlist Panel States)
- **Testability**: full (requires adding cards to wishlist first via the modal)
- **Priority**: medium

#### collection_multiselect_select_all_none
- **Filename**: `collection_multiselect_select_all_none`
- **Description**: In multi-select mode, I click "All" in the selection bar to select all visible cards. The count updates to show the total visible card count. I then click "None" to deselect all, and the count returns to 0.
- **UX Sections**: Flow 4.10 steps 3-4 (Select All/None), Section 3.3 (`sel-all`, `sel-none`)
- **Testability**: full
- **Priority**: medium

#### collection_multiselect_add_to_binder
- **Filename**: `collection_multiselect_add_to_binder`
- **Description**: In multi-select mode, I select one or more cards and click "Add to Binder" in the selection bar. The binder assignment modal opens with a dropdown of existing binders plus a "New Binder..." option. I select a binder and confirm, and the selected cards are assigned.
- **UX Sections**: Flow 4.10 step 5 (Add to Binder), Section 3.9 (Assign to Binder Modal)
- **Testability**: full
- **Priority**: medium

#### collection_multiselect_want
- **Filename**: `collection_multiselect_want`
- **Description**: In multi-select mode, I select several cards and click "Want" in the selection bar. All selected cards are added to the wishlist in bulk. The wishlist count in the More menu updates to reflect the added cards.
- **UX Sections**: Flow 4.10 step 5 (Want), Section 3.3 (`sel-want-btn`)
- **Testability**: full
- **Priority**: medium

#### collection_sidebar_open_close
- **Filename**: `collection_sidebar_open_close`
- **Description**: When I click the "Filters" button, the filter sidebar slides in from the left with a semi-transparent backdrop. Clicking "Close Filters" or the backdrop closes the sidebar. The sidebar contains all 13 filter dimensions organized in sections.
- **UX Sections**: Section 3.4 (Filter Sidebar), Section 7.4 (Sidebar States)
- **Testability**: full
- **Priority**: medium

#### collection_save_view
- **Filename**: `collection_save_view`
- **Description**: After applying some filters in the sidebar, I click "Save Current Filters as View" and enter a name in the prompt dialog. The view is saved and appears in the "Saved Views" dropdown. I can load it later to restore the same filter configuration.
- **UX Sections**: Flow 4.18 (Saving and Loading Views), Section 3.4 (Saved Views)
- **Testability**: full
- **Priority**: medium

#### collection_image_display_toggle
- **Filename**: `collection_image_display_toggle`
- **Description**: When I open the More menu, I see "Image Display" pills with "Crop" and "Contain" options. Selecting "Contain" changes card thumbnails to show the full card within their container. Selecting "Crop" returns to the cropped display. The setting persists.
- **UX Sections**: Flow 4.16 (Changing Image Display Mode), Section 3.2 (`image-display-pills`)
- **Testability**: full
- **Priority**: medium

#### collection_ordered_banner
- **Filename**: `collection_ordered_banner`
- **Description**: When the collection includes cards with "ordered" status, an orange-tinted banner appears at the top of the content area showing "N cards awaiting delivery" with a "View Ordered" button. Clicking "View Ordered" activates the ordered status filter.
- **UX Sections**: Section 5.6 (Ordered Banner), Section 3.12 (`ordered-banner`, `view-ordered-btn`), Section 7.10 (Ordered Banner State)
- **Testability**: limited (requires cards with "ordered" status in the test fixture; demo data may not include ordered cards)
- **Priority**: medium

#### collection_filter_status_disposition
- **Filename**: `collection_filter_status_disposition`
- **Description**: When I open the filter sidebar and select a disposition status filter (e.g., "Sold" or "Traded"), a server-side re-fetch occurs with `status=all`, and the collection displays cards matching that disposition. The Ordered and Wanted filters work client-side in contrast.
- **UX Sections**: Section 3.4 (Status Filter), Section 5.2 (Server-Side vs Client-Side Filtering)
- **Testability**: limited (requires cards with sold/traded status; test fixture may not include disposed cards)
- **Priority**: medium

### Low Priority

#### collection_include_unowned_cycle
- **Filename**: `collection_include_unowned_cycle`
- **Description**: After applying a set filter, I open the More menu and click "+ Unowned". On first click, base printings of unowned cards appear greyed out. On second click, it switches to full mode showing all printings. On third click, include-unowned turns off. The status text changes to show "N owned, N missing" while active. "Buy Missing" buttons appear in the More menu.
- **UX Sections**: Flow 4.11 (Include Unowned Mode), Section 5.9 (Include Unowned State Cycle), Section 7.8 (Include Unowned States)
- **Testability**: limited (requires a set filter with some unowned cards; test fixture has ~50 cards across 11 sets, so many set cards will be unowned)
- **Priority**: low

#### collection_buy_missing_cards
- **Filename**: `collection_buy_missing_cards`
- **Description**: With include-unowned active and a set filter applied, I open the More menu and click "Copy for Card Kingdom" or "Copy for TCGplayer". The unowned card list is copied to the clipboard, and the vendor website opens in a new tab.
- **UX Sections**: Flow 4.12 (Buy Missing Cards), Section 3.2 (`buy-missing-ck`, `buy-missing-tcg`)
- **Testability**: limited (clipboard copy is hard to verify in headless browser; external tab open cannot be observed)
- **Priority**: low

#### collection_price_floor_setting
- **Filename**: `collection_price_floor_setting`
- **Description**: When I open the More menu and enter a dollar amount in the "Price Floor" input, cards below that price are excluded from the total value calculation displayed in the status text. The status text value updates to reflect the floor.
- **UX Sections**: Flow 4.17 (Setting Price Floor), Section 3.2 (`price-floor-input`)
- **Testability**: limited (requires price data on cards to observe the total change)
- **Priority**: low

#### collection_table_filterable_click
- **Filename**: `collection_table_filterable_click`
- **Description**: In table view, filterable text elements (card name, type, set code, rarity, mana cost, date) are clickable. Clicking a filterable element (e.g., a set code) applies that value as a filter without opening the card modal. The filter sidebar reflects the applied filter.
- **UX Sections**: Section 5.10 (Filterable Element Click Propagation -- table view), Section 3.10 (Filterable cells)
- **Testability**: full
- **Priority**: low

#### collection_multiselect_share
- **Filename**: `collection_multiselect_share`
- **Description**: In multi-select mode, I select several cards and click "Share" in the selection bar. A Scryfall search URL is generated, shortened via `/api/shorten`, and displayed in the share result area.
- **UX Sections**: Flow 4.10 step 5 (Share), Section 3.3 (`sel-share-btn`, `sel-share-result`)
- **Testability**: limited (URL shortening depends on external service availability; the `/api/shorten` endpoint may not work in test containers)
- **Priority**: low

#### collection_multiselect_shift_select
- **Filename**: `collection_multiselect_shift_select`
- **Description**: In multi-select mode, I click one card checkbox, then shift-click another card checkbox further down the list. All cards between the two clicks are selected (range selection). The selection count updates accordingly.
- **UX Sections**: Flow 4.10 step 3 (shift-click range selection), Section 5.12 (Selection State)
- **Testability**: full
- **Priority**: low

#### collection_modal_dispose_copy
- **Filename**: `collection_modal_dispose_copy`
- **Description**: In the card detail modal's Copies section, I select a disposition (e.g., "Sold") from the dispose dropdown on a copy, optionally enter a price and note, and click the dispose button. The copy's status changes and the copies section updates.
- **UX Sections**: Flow 4.7 (Managing Per-Copy Data -- dispose), Section 3.6 (Dispose select/price/note/button)
- **Testability**: full
- **Priority**: low

#### collection_modal_receive_ordered
- **Filename**: `collection_modal_receive_ordered`
- **Description**: In the card detail modal for a card with an ordered copy, I click the "Receive" button on that copy. The copy's status changes from ordered to owned, and the copies section updates to reflect the new status.
- **UX Sections**: Flow 4.7 (Managing Per-Copy Data -- receive), Flow 4.19 (Receiving Ordered Cards -- individual), Section 3.6 (`receive-btn`)
- **Testability**: limited (requires a card with "ordered" status in the test fixture)
- **Priority**: low

#### collection_orders_receive_all
- **Filename**: `collection_orders_receive_all`
- **Description**: In orders view, each order group header has a "Receive All (N)" button. Clicking it marks all ordered cards in that order as received in a single API call. The order group updates to reflect the received status.
- **UX Sections**: Flow 4.19 step 2 (Bulk per order), Section 3.12 (`receive-all-btn`)
- **Testability**: limited (requires ordered cards in the test fixture grouped by order)
- **Priority**: low

#### collection_modal_move_between_containers
- **Filename**: `collection_modal_move_between_containers`
- **Description**: In the card detail modal, I move a copy currently assigned to a binder into a deck using the "Move to Deck" dropdown. The copy's assignment updates to show the new deck. I can then move it back to a binder using "Move to Binder".
- **UX Sections**: Flow 4.7 (Managing Per-Copy Data -- move between deck and binder), Section 3.6 (`copy-move-to-deck`, `copy-move-to-binder`)
- **Testability**: full (requires assigning to a binder first, then moving)
- **Priority**: low

#### collection_wishlist_clear_all
- **Filename**: `collection_wishlist_clear_all`
- **Description**: When the wishlist panel has entries and I click "Clear All", a confirmation dialog appears. After confirming, all wishlist entries are removed and the panel shows "Wishlist is empty". The wishlist count in the More menu updates to 0.
- **UX Sections**: Flow 4.9 step 6 (Clear All), Section 3.7 (`wl-clear-all`), Section 7.6 (Wishlist Panel States -- empty)
- **Testability**: full (requires adding cards to wishlist first)
- **Priority**: low

#### collection_empty_state
- **Filename**: `collection_empty_state`
- **Description**: When the collection has no cards and no filters are active, the main area shows a "No cards found" empty state message instead of an empty table or grid.
- **UX Sections**: Section 7.1 (Page-Level States -- Empty collection)
- **Testability**: limited (requires an instance with an empty collection; the test fixture includes demo data)
- **Priority**: low

#### collection_header_home_link
- **Filename**: `collection_header_home_link`
- **Description**: The page header contains "Collection" as a clickable link. Clicking it navigates back to the homepage at `/`.
- **UX Sections**: Section 2 (Navigation -- Header `<h1>` "Collection" link)
- **Testability**: full
- **Priority**: low

#### collection_virtual_scroll_grid
- **Filename**: `collection_virtual_scroll_grid`
- **Description**: In grid view with a large collection, the grid uses virtual scrolling -- only rendering visible rows plus a buffer. Scrolling through the grid progressively renders new cards while removing off-screen ones, maintaining smooth performance.
- **UX Sections**: Section 5.3 (Virtual Scrolling), Section 3.11 (Virtual scroll grid `vgrid`)
- **Testability**: limited (visual performance is difficult to assert; would need to verify that not all DOM elements are rendered simultaneously)
- **Priority**: low

#### collection_inline_binder_creation
- **Filename**: `collection_inline_binder_creation`
- **Description**: In the card detail modal's Copies section, I select "New Binder..." from the "Add to Binder" dropdown. After entering a binder name, the binder is created and the copy is assigned to it.
- **UX Sections**: Flow 4.7 (Managing Per-Copy Data -- create new binder inline), Section 3.6 (`copy-add-to-binder`)
- **Testability**: full
- **Priority**: low

#### collection_wishlist_copy_for_vendor
- **Filename**: `collection_wishlist_copy_for_vendor`
- **Description**: In the wishlist panel with entries, I click "Copy for CK" to copy the list in Card Kingdom format and open the CK builder, or "Copy for TCG" to copy in TCGplayer format and open mass entry.
- **UX Sections**: Flow 4.9 step 5 (Copy for CK / Copy for TCG), Section 3.7 (`wl-copy-ck`, `wl-copy-tcg`), Section 2 (Navigation -- external links)
- **Testability**: limited (clipboard copy and external tab open are hard to verify in headless browser)
- **Priority**: low

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| SS1 Page Purpose | `collection_status_text_updates`, `collection_view_toggle` (existing) |
| SS2 Navigation > Header home link | `collection_header_home_link` |
| SS2 Navigation > Modal "Full page" badge | `collection_modal_full_page_link` |
| SS2 Navigation > SF/CK price badges | `collection_card_modal_detail` (existing, partial) |
| SS2 Navigation > Order "Edit" link | `collection_orders_view` (existing, partial) |
| SS2 Navigation > Wishlist panel vendor links | `collection_wishlist_copy_for_vendor` |
| SS3.1 Header Controls > Search input | `collection_search_debounced` |
| SS3.1 Header Controls > View toggle buttons | `collection_view_toggle` (existing) |
| SS3.1 Header Controls > Filters toggle | `collection_sidebar_open_close` |
| SS3.1 Header Controls > Grid column controls | `collection_grid_column_resize` |
| SS3.1 Header Controls > Status text | `collection_status_text_updates` |
| SS3.2 More Menu > Include unowned | `collection_include_unowned_cycle` |
| SS3.2 More Menu > Buy Missing buttons | `collection_buy_missing_cards` |
| SS3.2 More Menu > Wishlist toggle | `collection_wishlist_panel` |
| SS3.2 More Menu > Toggle Multi-Select | `collection_multiselect_toggle` |
| SS3.2 More Menu > Image Display pills | `collection_image_display_toggle` |
| SS3.2 More Menu > Price Floor input | `collection_price_floor_setting` |
| SS3.3 Selection Bar | `collection_multiselect_toggle`, `collection_multiselect_select_all_none` |
| SS3.3 Selection Bar > Want | `collection_multiselect_want` |
| SS3.3 Selection Bar > Share | `collection_multiselect_share` |
| SS3.3 Selection Bar > Add to Deck | `collection_multiselect_new_deck` (existing) |
| SS3.3 Selection Bar > Add to Binder | `collection_multiselect_add_to_binder` |
| SS3.3 Selection Bar > Delete | `collection_multiselect_delete` |
| SS3.4 Filter Sidebar > Saved Views | `views_save_and_load` (existing), `views_container_only_filter` (existing), `collection_save_view` |
| SS3.4 Filter Sidebar > Color filter | `collection_filter_color` |
| SS3.4 Filter Sidebar > Rarity filter | `collection_filter_rarity` (existing) |
| SS3.4 Filter Sidebar > Set filter | `collection_filter_set` |
| SS3.4 Filter Sidebar > Type filter | `collection_filter_type` |
| SS3.4 Filter Sidebar > Subtype filter | `collection_filter_subtype` |
| SS3.4 Filter Sidebar > CN range | `collection_filter_cn_range` |
| SS3.4 Filter Sidebar > CMC range | `collection_filter_cmc_range` |
| SS3.4 Filter Sidebar > Finish filter | `collection_filter_finish` |
| SS3.4 Filter Sidebar > Status filter | `collection_filter_status_disposition` |
| SS3.4 Filter Sidebar > Treatment filter | `collection_filter_treatment` |
| SS3.4 Filter Sidebar > Price range | `collection_filter_price_range` |
| SS3.4 Filter Sidebar > Date range | `collection_filter_date_range` |
| SS3.4 Filter Sidebar > Container filter | `collection_deck_binder_filter` (existing) |
| SS3.4 Filter Sidebar > Clear Filters | `collection_clear_filters` |
| SS3.5 Column Configuration Drawer | `collection_column_config` |
| SS3.6 Card Detail Modal > Open/close | `collection_card_modal_detail` (existing), `collection_modal_close` (existing), `collection_modal_escape_close`, `collection_modal_backdrop_close` |
| SS3.6 Card Detail Modal > DFC flip | `collection_modal_dfc_flip` |
| SS3.6 Card Detail Modal > Want button | `collection_modal_want_button` |
| SS3.6 Card Detail Modal > Add to Collection form | `collection_add_from_modal` (existing), `collection_add_second_card_no_refresh` (existing) |
| SS3.6 Card Detail Modal > Per-copy: Receive | `collection_modal_receive_ordered` |
| SS3.6 Card Detail Modal > Per-copy: Dispose | `collection_modal_dispose_copy` |
| SS3.6 Card Detail Modal > Per-copy: Delete | `collection_modal_delete_copy` |
| SS3.6 Card Detail Modal > Per-copy: Reprocess/Refinish | *not covered* (requires image-ingested cards, not available in test fixture) |
| SS3.6 Card Detail Modal > Per-copy: Deck assignment | `collection_inline_deck_creation` (existing), `collection_modal_copy_deck_assignment` |
| SS3.6 Card Detail Modal > Per-copy: Binder assignment | `collection_modal_copy_binder_assignment`, `collection_inline_binder_creation` |
| SS3.6 Card Detail Modal > Per-copy: Remove from deck/binder | `collection_modal_copy_deck_assignment`, `collection_modal_copy_binder_assignment` |
| SS3.6 Card Detail Modal > Per-copy: Move between containers | `collection_modal_move_between_containers` |
| SS3.6 Card Detail Modal > Price History Chart | `collection_price_chart` (existing) |
| SS3.6 Card Detail Modal > Filterable elements | `collection_modal_filterable_click` |
| SS3.7 Wishlist Panel | `collection_wishlist_panel` |
| SS3.7 Wishlist Panel > Remove entry | `collection_wishlist_panel` |
| SS3.7 Wishlist Panel > Copy for CK/TCG | `collection_wishlist_copy_for_vendor` |
| SS3.7 Wishlist Panel > Clear All | `collection_wishlist_clear_all` |
| SS3.8 Assign to Deck Modal | `collection_multiselect_new_deck` (existing) |
| SS3.9 Assign to Binder Modal | `collection_multiselect_add_to_binder` |
| SS3.10 Table View Elements > Sortable headers | `collection_sort_table_columns` |
| SS3.10 Table View Elements > Filterable cells | `collection_table_filterable_click` |
| SS3.10 Table View Elements > Select-all checkbox | `collection_multiselect_select_all_none` |
| SS3.10 Table View Elements > Shift-click range | `collection_multiselect_shift_select` |
| SS3.11 Grid View Elements > Sort bar | `collection_grid_sort_bar` |
| SS3.11 Grid View Elements > Virtual scroll | `collection_virtual_scroll_grid` |
| SS3.12 Orders View Elements > Order groups | `collection_orders_view` (existing) |
| SS3.12 Orders View Elements > Receive All | `collection_orders_receive_all` |
| SS3.12 Orders View Elements > Ordered banner | `collection_ordered_banner` |
| Flow 4.1 Basic Browsing | `collection_status_text_updates`, `collection_view_toggle` (existing) |
| Flow 4.2 Searching | `collection_search_debounced` |
| Flow 4.3 Filtering | `collection_filter_rarity` (existing), `collection_filter_color`, `collection_filter_type`, `collection_filter_set`, and all other filter intents |
| Flow 4.4 Switching Views | `collection_view_toggle` (existing), `collection_orders_view` (existing) |
| Flow 4.5 Viewing Card Details | `collection_card_modal_detail` (existing), `collection_modal_close` (existing), `collection_modal_escape_close`, `collection_modal_backdrop_close`, `collection_modal_dfc_flip` |
| Flow 4.6 Filterable Click in Modal | `collection_modal_filterable_click` |
| Flow 4.7 Managing Per-Copy Data | `collection_inline_deck_creation` (existing), `collection_modal_copy_deck_assignment`, `collection_modal_copy_binder_assignment`, `collection_modal_delete_copy`, `collection_modal_dispose_copy`, `collection_modal_receive_ordered`, `collection_modal_move_between_containers` |
| Flow 4.8 Adding Card from Modal | `collection_add_from_modal` (existing), `collection_add_second_card_no_refresh` (existing) |
| Flow 4.9 Wishlist Management | `collection_modal_want_button`, `collection_wishlist_panel`, `collection_wishlist_clear_all`, `collection_wishlist_copy_for_vendor` |
| Flow 4.10 Multi-Select Operations | `collection_multiselect_toggle`, `collection_multiselect_select_all_none`, `collection_multiselect_new_deck` (existing), `collection_multiselect_add_to_binder`, `collection_multiselect_want`, `collection_multiselect_share`, `collection_multiselect_delete`, `collection_multiselect_shift_select` |
| Flow 4.11 Include Unowned | `collection_include_unowned_cycle` |
| Flow 4.12 Buy Missing | `collection_buy_missing_cards` |
| Flow 4.13 Sorting | `collection_sort_table_columns`, `collection_grid_sort_bar` |
| Flow 4.14 Column Config | `collection_column_config` |
| Flow 4.15 Grid Size | `collection_grid_column_resize` |
| Flow 4.16 Image Display | `collection_image_display_toggle` |
| Flow 4.17 Price Floor | `collection_price_floor_setting` |
| Flow 4.18 Saving/Loading Views | `views_save_and_load` (existing), `views_container_only_filter` (existing), `collection_save_view` |
| Flow 4.19 Receiving Ordered | `collection_modal_receive_ordered`, `collection_orders_receive_all`, `collection_ordered_banner` |
| Flow 4.20 Container Filtering | `collection_deck_binder_filter` (existing) |
| SS5.1 Initial Load Sequence | `collection_status_text_updates` (verifies data loaded) |
| SS5.2 Client vs Server Filtering | `collection_search_debounced` (server), `collection_filter_color` (client), `collection_filter_status_disposition` (server) |
| SS5.3 Virtual Scrolling | `collection_virtual_scroll_grid` |
| SS5.4 Debouncing | `collection_search_debounced` |
| SS5.5 Modal Lazy Loading | `collection_price_chart` (existing), `collection_card_modal_detail` (existing) |
| SS5.6 Ordered Banner | `collection_ordered_banner` |
| SS5.9 Include Unowned State Cycle | `collection_include_unowned_cycle` |
| SS5.10 Filterable Click Propagation | `collection_modal_filterable_click`, `collection_table_filterable_click` |
| SS5.11 Wishlist Synchronization | `collection_modal_want_button`, `collection_wishlist_panel`, `collection_multiselect_want` |
| SS5.12 Selection State | `collection_multiselect_toggle`, `collection_multiselect_shift_select` |
| SS7.1 Page-Level States | `collection_empty_state`, `collection_status_text_updates` |
| SS7.2 View Mode States | `collection_view_toggle` (existing), `collection_orders_view` (existing) |
| SS7.3 Card Visual States | `collection_filter_finish` (foil), `collection_include_unowned_cycle` (unowned greyed out) |
| SS7.4 Sidebar States | `collection_sidebar_open_close` |
| SS7.5 Modal States | `collection_card_modal_detail` (existing), `collection_modal_dfc_flip`, `collection_price_chart` (existing), `collection_add_from_modal` (existing) |
| SS7.6 Wishlist Panel States | `collection_wishlist_panel`, `collection_wishlist_clear_all` |
| SS7.7 Selection Bar States | `collection_multiselect_toggle` |
| SS7.8 Include Unowned States | `collection_include_unowned_cycle` |
| SS7.9 More Menu States | `collection_multiselect_toggle` (opens More menu), `collection_include_unowned_cycle` |
| SS7.10 Ordered Banner State | `collection_ordered_banner` |

## Intentionally Not Covered

The following areas from the UX description are **not** covered by intents because they are untestable in the headless browser test harness or require external dependencies:

- **Reprocess/Refinish buttons** (Section 3.6) -- Only shown for image-ingested cards. The test fixture does not include image-ingested cards with ingest lineage, and triggering the ingest pipeline is outside the scope of collection page tests.
- **External vendor link behavior** (Section 2 -- Scryfall, Card Kingdom, TCGplayer links) -- These open external websites. We can verify the links exist and have correct `href` values, but cannot follow them in test containers.
- **Clipboard copy operations** (Buy Missing, Wishlist Copy for CK/TCG, Share) -- The clipboard API is not reliably testable in headless Playwright. Marked as limited testability where covered.
- **localStorage persistence across reloads** (Column config, grid column count) -- Would require a page reload within the test, which resets harness state. Verifying the in-session behavior is sufficient.
- **Settings persistence via PUT /api/settings** (Image display, price floor) -- The API call can be verified, but confirming persistence across page loads requires a reload.
- **Performance characteristics** (Virtual scrolling smoothness, debounce timing) -- These are runtime performance properties that cannot be meaningfully asserted in screenshot-based tests.

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 10 | `collection_search_debounced`, `collection_filter_color`, `collection_filter_type`, `collection_sort_table_columns`, `collection_modal_escape_close`, `collection_modal_backdrop_close`, `collection_multiselect_toggle`, `collection_multiselect_delete`, `collection_clear_filters`, `collection_status_text_updates` |
| Medium | 24 | `collection_filter_set`, `collection_filter_finish`, `collection_filter_treatment`, `collection_filter_cmc_range`, `collection_filter_price_range`, `collection_filter_date_range`, `collection_filter_subtype`, `collection_filter_cn_range`, `collection_column_config`, `collection_grid_column_resize`, `collection_grid_sort_bar`, `collection_modal_filterable_click`, `collection_modal_full_page_link`, `collection_modal_want_button`, `collection_modal_copy_deck_assignment`, `collection_modal_copy_binder_assignment`, `collection_modal_delete_copy`, `collection_modal_dfc_flip`, `collection_wishlist_panel`, `collection_multiselect_select_all_none`, `collection_multiselect_add_to_binder`, `collection_multiselect_want`, `collection_sidebar_open_close`, `collection_save_view`, `collection_image_display_toggle`, `collection_ordered_banner`, `collection_filter_status_disposition` |
| Low | 16 | `collection_include_unowned_cycle`, `collection_buy_missing_cards`, `collection_price_floor_setting`, `collection_table_filterable_click`, `collection_multiselect_share`, `collection_multiselect_shift_select`, `collection_modal_dispose_copy`, `collection_modal_receive_ordered`, `collection_orders_receive_all`, `collection_modal_move_between_containers`, `collection_wishlist_clear_all`, `collection_empty_state`, `collection_header_home_link`, `collection_virtual_scroll_grid`, `collection_inline_binder_creation`, `collection_wishlist_copy_for_vendor` |

**Total new intents: 50** (plus 13 existing: `collection_add_from_modal`, `collection_add_second_card_no_refresh`, `collection_card_modal_detail`, `collection_deck_binder_filter`, `collection_filter_rarity`, `collection_inline_deck_creation`, `collection_modal_close`, `collection_multiselect_new_deck`, `collection_orders_view`, `collection_price_chart`, `collection_view_toggle`, `views_container_only_filter`, `views_save_and_load`)

## Limited Testability Summary

The following proposed intents have limited testability and may require special fixture data or have inherent harness limitations:

| Intent | Limitation |
|---|---|
| `collection_filter_treatment` | Requires cards with special treatments (borderless, showcase, etc.) in test fixture |
| `collection_filter_price_range` | Requires cards with populated price data |
| `collection_modal_dfc_flip` | Requires a double-faced card in test fixture |
| `collection_ordered_banner` | Requires cards with "ordered" status |
| `collection_filter_status_disposition` | Requires cards with sold/traded/gifted/lost status |
| `collection_include_unowned_cycle` | Requires set filter with unowned cards (likely available with 11-set fixture) |
| `collection_buy_missing_cards` | Clipboard and external tab open untestable |
| `collection_price_floor_setting` | Requires price data to observe value change |
| `collection_multiselect_share` | URL shortening may not work in test containers |
| `collection_modal_receive_ordered` | Requires cards with "ordered" status |
| `collection_orders_receive_all` | Requires ordered cards grouped by order |
| `collection_empty_state` | Requires empty collection instance |
| `collection_virtual_scroll_grid` | Performance assertion is difficult in screenshot tests |
| `collection_wishlist_copy_for_vendor` | Clipboard and external tab open untestable |
