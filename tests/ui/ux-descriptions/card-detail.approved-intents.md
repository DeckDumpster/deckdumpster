# Card Detail Page -- Approved Intents

Source: `tests/ui/ux-descriptions/card-detail.test-plan.md` (28 proposed)
Existing intents: 12

Review date: 2026-03-09

---

## Review Summary

The test plan proposed 28 new intents on top of 12 existing ones, which would bring the total to 40. That is far too many for a single page. The existing 12 intents already cover the core user flows (load, flip DFC, want, add, delete, dispose, receive, deck assign, history, price chart, not-found error, collection modal navigation). The review below cuts aggressively: merging overlapping proposals, dropping anything that duplicates existing coverage with minor variation, and deferring low-ROI or CSS-only concerns.

---

## Implement Now

These fill genuine, testable gaps not covered by the existing 12 intents.

### 1. `card_detail_binder_assign`

**Priority**: high

**Description**: On the card detail page, an unassigned copy shows an "Add to Binder" dropdown listing all existing binders. Selecting a binder assigns the copy. After assignment, the copy shows the binder name with a "Remove" link and a "Move to Deck" dropdown instead of the assignment dropdowns.

**Rationale**: The existing `card_detail_deck_assign` only covers deck assignment. Binder assignment is the symmetric operation and exercises a completely different API path (`POST /api/binders/:id/cards`). The fixture has binders ("Trade Binder", "Foil Collection") and unassigned owned cards (e.g., `fdn/139` Cathar Commando) to test against.

**What it replaces from the test plan**: Absorbs `card_detail_binder_assign`, `card_detail_remove_from_binder` (the remove link is verified as part of the post-assignment state).

---

### 2. `card_detail_move_deck_to_binder`

**Priority**: medium

**Description**: On the card detail page, when a copy is assigned to a deck, a "Move to Binder" dropdown appears alongside the deck name and "Remove" link. Selecting a binder from the dropdown atomically moves the copy from the deck to the binder. After the move, the copy shows the binder name with a "Remove" link and a "Move to Deck" dropdown.

**Rationale**: Cross-container moves are a distinct atomic operation (`POST /api/binders/:id/cards/move`) that is not tested by either `card_detail_deck_assign` or the proposed `card_detail_binder_assign`. The fixture has cards in decks (e.g., `fdn/100` Beast-Kin Ranger in "Bolt Tribal") and binders to move them to.

**What it replaces from the test plan**: Absorbs `card_detail_move_deck_to_binder` and `card_detail_move_binder_to_deck` (only one direction needs explicit testing -- the API pattern is identical and the inverse is implicitly validated when the destination state renders correctly).

---

### 3. `card_detail_dispose_listed_unlist`

**Priority**: medium

**Description**: On the card detail page, I select "Listed" from the disposition dropdown on an owned copy. After confirming, the copy shows a purple "Listed" badge. The disposition dropdown now includes an "Unlist" option. Selecting "Unlist" returns the copy to "owned" status, and the full disposition controls reappear.

**Rationale**: The existing `card_detail_dispose_copy` covers sold/traded/gifted/lost (terminal dispositions). Listed/Unlist is the only reversible disposition and exercises a round-trip status change that no existing intent covers. This also validates the purple badge rendering.

**What it replaces from the test plan**: Absorbs `card_detail_dispose_listed_unlist` and the relevant parts of `card_detail_disposition_badges` (the purple badge is verified as part of this flow).

---

### 4. `card_detail_flip_non_dfc`

**Priority**: medium

**Description**: When I view a non-double-faced card (e.g., `fdn/100` Beast-Kin Ranger, layout "normal") and click the flip button, the card image flips to show the generic card back. The details panel does not change. Clicking the flip button again returns to the front face.

**Rationale**: The existing `card_detail_dfc_flip` only covers double-faced cards where the flip updates the details panel. Non-DFC flip is a different code path (details panel stays unchanged, back image is the static card back). The fixture has plenty of normal-layout cards to test with. NOTE: The test fixture currently has NO actual DFC cards (all are "normal" or "adventure" layout), so the existing `card_detail_dfc_flip` may itself need fixture attention. This non-DFC test is reliable with current data.

---

### 5. `card_detail_add_form_toggle`

**Priority**: medium

**Description**: On the card detail page, clicking the "Add" button opens the add-to-collection form with a date field pre-filled with today's date, a price field, and a source field. Clicking "Add" again while the form is open closes it without submitting. No copy is added.

**Rationale**: The existing `card_detail_add_copy` covers the full add-and-confirm flow but does not test the toggle-to-close behavior. This is a distinct interaction (open then close without side effects) that validates the form's toggle state management.

**What it replaces from the test plan**: Absorbs `card_detail_add_form_toggle`. Drops `card_detail_add_form_submitting_state` -- the "Adding..." transient button text is a sub-second state that the existing `card_detail_add_copy` already exercises end-to-end.

---

## Deferred

### Not implementing -- Redundant with existing intents

| Proposed Intent | Why Deferred |
|---|---|
| `card_detail_metadata_display` | Redundant with `card_detail_direct_navigation`, which already verifies "card's name, mana cost, type line, set with keyrune icon, collector number, rarity, and artist" plus external link badges. The only additions (oracle name, mana value, treatment tags) are edge cases that depend on specific card data and add minimal regression value. |
| `card_detail_external_links` | Already covered by `card_detail_direct_navigation`, which verifies "External links to Scryfall and Card Kingdom appear as badges." Testing `target="_blank"` is an HTML attribute check, not a behavioral test. |
| `card_detail_site_header_nav` | The site header is identical on every page. Testing nav links on the card detail page specifically has no value beyond what any other page's test provides. |
| `card_detail_copies_section_header` | The "Copies (N)" header is implicitly verified by every intent that adds, deletes, or disposes of copies (`card_detail_add_copy`, `card_detail_delete_copy`, `card_detail_dispose_copy`). |
| `card_detail_copy_card_fields` | Copy fields (finish, condition, source, date, ID) are visible in every copy-related intent. No separate test needed for reading static text already shown in 6+ existing scenarios. |
| `card_detail_add_form_submitting_state` | The "Adding..." transient button state lasts milliseconds. The existing `card_detail_add_copy` already covers the full submit flow. Testing a sub-second loading indicator in a screenshot-based test is unreliable. |
| `card_detail_remove_from_deck` | The "Remove" link after deck assignment is already verified as part of `card_detail_deck_assign` (the intent confirms "Remove link" appears). The click-to-remove action is the inverse of assign and returns to the same state the test started from. |
| `card_detail_remove_from_binder` | Same reasoning as remove-from-deck. Verified as post-state in the proposed `card_detail_binder_assign`. |
| `card_detail_move_binder_to_deck` | The inverse of `card_detail_move_deck_to_binder`. Same API pattern (`/move`), same UI pattern. One direction is sufficient. |
| `card_detail_copy_history_events` | The existing `card_detail_copy_history` already covers expanding the timeline and seeing events. Adding a separate intent to check green vs. blue dot colors is a CSS-level concern. |
| `card_detail_copy_history_empty` | "No history" text for a fresh copy is a trivial empty-state string. Low value. |
| `card_detail_wishlist_persists_on_load` | The existing `card_detail_want_toggle` tests the want/unwant flow. Whether the "Wanted" state persists on reload is an API state check, not a new UI interaction. |
| `card_detail_receive_button_only_ordered` | The existing `card_detail_receive_copy` already starts with an ordered copy showing the Receive button. Verifying its absence on owned copies is a negative test with no user-facing behavior to validate. |
| `card_detail_delete_only_owned_ordered` | Same reasoning. The existing `card_detail_delete_copy` shows the Delete button on a valid copy. Verifying its absence on disposed copies is a negative test. |

### Not implementing -- Untestable or impractical

| Proposed Intent | Why Deferred |
|---|---|
| `card_detail_page_title` | Browser tab title (`document.title`) is not visible in a screenshot. Claude Vision cannot validate it. Would require Playwright-specific assertion outside the screenshot harness. |
| `card_detail_invalid_url_format` | The existing `card_detail_not_found` already tests navigating to a bad URL and seeing an error. The distinction between "invalid URL format" vs. "valid format but card not found" is an implementation detail, not a user-meaningful difference. Both show an error state. |
| `card_detail_new_deck_from_assign` | Requires interacting with a browser `prompt()` dialog to enter a deck name. The test plan itself notes "limited testability" for this. Claude Vision cannot validate or interact with native browser dialogs. |
| `card_detail_new_binder_from_assign` | Same browser `prompt()` limitation. |
| `card_detail_disposition_badges` | Would require disposing of copies with 5 different statuses and verifying badge colors. The color differences (green vs. yellow vs. blue vs. red vs. purple) are CSS-level concerns. The `card_detail_dispose_copy` and `card_detail_dispose_listed_unlist` intents already verify the badges appear after disposition. |
| `card_detail_price_chart_range_pills_disabled` | The existing `card_detail_price_chart` already tests range pills. Verifying disabled vs. enabled state depends on the exact date range of price data, which varies per fixture. The test plan calls this "full testability" but it requires precise control over price data time spans. |
| `card_detail_price_chart_hidden_no_data` | The test fixture currently has NO price history data for ANY card (`/api/price-history/fdn/100` returns `{}`). This means the chart is always hidden. There is nothing to verify -- the section simply is not rendered. |
| `card_detail_price_chart_purchase_lines` | Chart.js renders on `<canvas>`. Dashed green lines at purchase price levels are pixel-level rendering details that cannot be reliably validated via Claude Vision screenshots. |
| `card_detail_mobile_layout` | Responsive layout testing (below 768px viewport) is a CSS concern. The screenshot harness would need viewport resizing support, and the validation is purely visual (column vs. row flex direction). Low regression risk. |

---

## Final Tally

| Category | Count |
|---|---|
| Existing intents (unchanged) | 12 |
| New intents approved | 5 |
| Proposed intents cut | 23 |
| **Total after approval** | **17** |

The 5 approved intents target genuine coverage gaps: binder assignment (symmetric to deck), cross-container moves (atomic operation), listed/unlist (reversible disposition), non-DFC flip (different code path), and add-form toggle (distinct from add-and-confirm).
