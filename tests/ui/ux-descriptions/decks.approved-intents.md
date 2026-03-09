# Decks List Page (`/decks`) -- Approved Intents

Reviewed: 2026-03-09
Source: `decks.test-plan.md` (17 proposed) + 5 existing intents

---

## Review Summary

The test plan proposed 17 new intents. After review against the live fixture data
(2 decks: "Bolt Tribal" modern w/ 11 cards, "Eldrazi Ramp" commander w/ 6 cards)
and the 5 existing intents, the list is reduced to **6 approved intents** for
implementation now, with 3 deferred and 8 cut entirely.

### Existing Coverage (no changes needed)

These 5 intents already exist and cover the core happy paths well:

| Intent | What it covers |
|--------|----------------|
| `deck_list_links_to_standalone_detail` | Flow 2: click card -> navigate to `/decks/:id` |
| `deck_create_redirects_to_detail` | Flow 3: create deck (name + format) -> redirect to detail |
| `decks_create_and_add_cards` | Create deck, verify it appears in list, open it, add cards |
| `decks_precon_origin_metadata` | Flow 4: precon checkbox toggle, origin fields, save + verify |
| `decks_delete_keeps_cards` | Delete deck, cards stay in collection |

---

## Approved: Implement Now (6 intents)

### 1. `decks_list_card_content`

**Description**: When I visit `/decks` with existing decks, each deck card in the grid displays the deck name as a heading, a format badge (e.g. "modern", "commander") if a format is set, the card count, and the description text. The fixture has "Bolt Tribal" (modern, 11 cards, "Burn deck") and "Eldrazi Ramp" (commander, 6 cards, "Big mana Eldrazi"). All of these data points are visible on each card without clicking into it.

**Rationale**: The existing intents verify navigation and creation but none verify the *content rendering* of deck cards in the list view. This is the highest-value gap -- if the grid rendering breaks, no existing test catches it.

**Priority**: high

---

### 2. `decks_create_modal_opens`

**Description**: When I visit `/decks` and click the "New Deck" button, a modal opens with the title "New Deck". The modal contains form fields: Name (placeholder "My Commander Deck"), Format (dropdown with commander, standard, modern, pioneer, legacy, vintage, pauper), Description (textarea), a "Preconstructed deck" checkbox, Sleeve Color, Deck Box, and Storage Location. Save and Cancel buttons are visible at the bottom. The precon-specific fields (Origin Set, Theme, Variation) are hidden until the checkbox is checked.

**Rationale**: `deck_create_redirects_to_detail` tests the end-to-end create flow but does not verify the modal's field inventory. If a field is removed or renamed, only this test catches it.

**Priority**: high

---

### 3. `decks_create_modal_validation`

**Description**: When I open the "New Deck" modal and click "Save" without entering a name, a browser alert appears with the message "Name is required". The modal remains open and no deck is created. I can then enter a name and successfully save.

**Rationale**: The only validation path in the create flow. Trivial to test, high regression value -- a broken guard means empty-named decks in the database.

**Priority**: high

---

### 4. `decks_list_empty_state`

**Description**: When I visit `/decks` on an instance with no decks, I see the message "No decks yet. Click 'New Deck' to create one." instead of a deck grid. The "New Deck" button is still available. To reach this state, I first delete both existing fixture decks via the API, then reload the page.

**Rationale**: The empty-to-populated transition is a common source of rendering bugs. The test plan flagged this as "limited" testability, but it is achievable by deleting fixture decks first. Worth the setup cost.

**Priority**: medium

---

### 5. `decks_create_minimal`

**Description**: When I open the "New Deck" modal, enter only a deck name (the sole required field), leave all other fields at their defaults, and click "Save", the deck is created and the browser navigates to the new deck's detail page at `/decks/:id`. The detail page shows the name I entered and no format, description, or precon metadata.

**Rationale**: `deck_create_redirects_to_detail` fills in name *and* format. This intent verifies that truly minimal input (name only) works. It catches regressions where optional-field handling breaks the POST.

**Priority**: medium

---

### 6. `decks_create_modal_backdrop_close`

**Description**: When I open the "New Deck" modal and click on the dark backdrop area outside the modal content, the modal closes without creating a deck. The deck list remains unchanged.

**Rationale**: Backdrop-click dismiss is a shared modal pattern used across the entire app. If the event listener regresses here, it regresses everywhere. One test covers the pattern.

**Priority**: medium

---

## Deferred (3 intents -- implement later if time permits)

### `decks_list_page_structure`
**Reason for deferral**: The legacy header ("MTG / Decks" with no site nav bar) is a known tech debt item. Testing its exact structure locks in behavior that may change soon. The MTG home link is already implicitly exercised by every test that starts on `/decks`. Defer until the header is standardized.

### `decks_create_full_fields`
**Reason for deferral**: This is the inverse of `decks_create_minimal` -- fill every field. The marginal value over the existing `deck_create_redirects_to_detail` (which already tests name + format) is low. The precon fields are covered by `decks_precon_origin_metadata`. Sleeve/deckbox/location are simple text fields with no special rendering or validation. Defer.

### `decks_list_precon_badge`
**Reason for deferral**: The fixture data has no precon decks. Testing this requires creating a precon deck first (covered by `decks_precon_origin_metadata`), then navigating back to the list to verify the badge. That makes it a multi-step compound test. Better to add once precon decks are in the fixture data.

---

## Cut (8 intents -- not worth implementing)

| Proposed Intent | Reason for Cut |
|----------------|----------------|
| `decks_list_card_links` | Fully redundant with existing `deck_list_links_to_standalone_detail`. Both verify the same thing: deck cards are `<a>` tags linking to `/decks/:id`. |
| `decks_list_responsive_grid` | CSS layout testing. Claude Vision screenshot comparison cannot reliably detect column count changes at different viewport widths. Better suited for a visual regression tool (Percy, Chromatic), not an intent-based scenario. |
| `decks_list_mtg_home_link` | Trivially low value. A single `<a href="/">` in a `<h1>`. If this breaks, literally every other test that navigates away from `/decks` would also fail. Not worth a dedicated scenario. |
| `decks_create_modal_precon_toggle` | Fully redundant with existing `decks_precon_origin_metadata`, which already tests checking the checkbox, seeing the fields appear, filling them in, and verifying the saved result. |
| `decks_create_modal_cancel` | Very low regression risk. Cancel just removes the `.active` class. If cancel breaks, backdrop-close (approved above) would also break since they share the same `closeModal()` function. One test for the dismiss pattern is enough. |
| `decks_list_card_hover_effect` | CSS hover state. Cannot be reliably verified via screenshot -- requires precise mouse positioning and timing. Untestable with the current harness. |
| `decks_list_no_loading_indicator` | Testing the *absence* of a feature is not meaningful regression coverage. The test would pass trivially (no spinner exists) and would never fail unless someone *adds* a spinner, which would be intentional. |
| `decks_list_format_badges` | Subsumed by `decks_list_card_content` (approved above), which already verifies that format badges appear on deck cards. A separate intent just for badges is redundant. |
| `decks_list_value_display` | Fixture decks have `total_value: 0` for both decks, so the value field is not rendered. Untestable with current fixture data. Even with priced cards, this is a simple conditional render -- low regression risk. |
| `decks_list_storage_location_display` | Fixture decks have `storage_location: null` for both. Untestable with current fixture. Same reasoning as value display. |

---

## Final Tally

| Category | Count |
|----------|-------|
| Existing (keep as-is) | 5 |
| Approved (implement now) | 6 |
| Deferred | 3 |
| Cut | 8 |
| **Total proposed** | **17** |
| **Net new to implement** | **6** |
