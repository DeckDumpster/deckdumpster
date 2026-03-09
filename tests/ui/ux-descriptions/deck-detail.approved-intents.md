# Deck Detail Page -- Approved Intents

**Reviewed:** 2026-03-09
**Reviewer role:** Product manager
**Input:** `deck-detail.test-plan.md` (16 proposed intents: 2a through 2p)

---

## Existing Coverage Summary

There are 13 existing deck-related intents across `deck_detail_*` and `decks_*` files. Before approving anything new, here is what is already tested:

| Flow | Existing Intent(s) | Verdict |
|---|---|---|
| Page load, metadata, card table | `deck_detail_direct_navigation` | Solid |
| Card name links to `/card/:set/:cn` | `deck_detail_card_links_to_card_page` | Solid |
| Delete deck + redirect | `deck_detail_delete_redirects_to_list`, `decks_delete_keeps_cards` | Solid (both UI flow and data side effect) |
| Create deck -> detail redirect | `deck_create_redirects_to_detail` | Solid |
| Deck list -> detail navigation | `deck_list_links_to_standalone_detail` | Solid |
| Add cards to deck | `decks_create_and_add_cards` | Partial (legacy inline view, not standalone page) |
| Import expected + completeness | `decks_import_expected_and_completeness` | Solid |
| Reassemble missing cards | `decks_reassemble_unassigned_cards` | Solid |
| Precon origin metadata | `decks_precon_origin_metadata` | Solid |
| Deck/binder exclusivity | `decks_exclusivity_enforcement` | Solid (not deck-detail-specific) |
| Card modal deck assignment | `decks_manage_from_card_modal` | Solid (not deck-detail-specific) |
| CSV import decklist | `decks_import_moxfield_decklist` | Solid (not deck-detail-specific) |

---

## Decisions on All 16 Proposed Intents

### APPROVED -- Implement Now (3 intents)

These fill genuine, high-value gaps in core CRUD flows on the standalone deck detail page.

#### 1. `deck_detail_zone_tab_switching` (was 2a)

**Approve.** Zone switching is the primary in-page navigation and has zero existing coverage. Deck 1 (Bolt Tribal) has 8 mainboard + 3 sideboard + 0 commander, which is ideal test data: two populated zones and one empty zone to verify "No cards in this zone". This is a pure read-only visual test with no destructive side effects.

- Covers: Flow 2, State 4, State 5
- Test data: Bolt Tribal deck 1 (mainboard: 8, sideboard: 3, commander: 0) -- verified on container

#### 2. `deck_detail_select_and_remove_cards` (was 2b)

**Approve.** Card removal is a core CRUD operation with no existing coverage. Selecting checkboxes, clicking "Remove Selected", and verifying the table updates plus count decrements is a high-signal test. Skip the "no selection alert" edge case (that is proposed separately as 2m and is cut below).

- Covers: Flow 3, State 4
- Test data: Bolt Tribal has 11 cards to work with

#### 3. `deck_detail_edit_properties` (was 2c)

**Approve.** The edit modal is the only way to modify deck metadata on the standalone page and has no dedicated test. The existing `decks_precon_origin_metadata` only tests precon creation, not editing an existing deck's name/format. Open modal, change name and format, save, verify header updates.

- Covers: Flow 4, State 11, Flow 10 (modal close on save)
- Test data: Any existing deck

### APPROVED -- Implement Next (1 intent)

#### 4. `deck_detail_add_cards_from_collection` (was 2d)

**Approve, but defer behind the three above.** The existing `decks_create_and_add_cards` was written against the legacy inline view. The standalone page's add-cards modal (search picker, zone selector, "Add Selected" button) is a different UI and needs its own test. There are 14 unassigned cards on the container to search for.

- Covers: Flow 5, State 12, State 13
- Test data: 14 unassigned cards including "Cathar Commando", "Infernal Vessel", etc.
- Note: This is the most complex test to implement (search, select, zone, add) so defer it slightly.

### CUT (12 intents)

#### 2e. `deck_detail_completeness_toggle` -- CUT

**Reason: Low signal, trivial interaction.** Clicking a header to expand/collapse a section is a generic CSS toggle. The completeness section's actual content (present/missing/extra groups, location tags, reassembly) is already tested by `decks_import_expected_and_completeness` and `decks_reassemble_unassigned_cards`. Verifying that a CSS class toggles visibility does not justify an entire scenario test that costs Claude API calls.

#### 2f. `deck_detail_completeness_hidden_without_expected` -- CUT

**Reason: Proving absence is weak, and the test plan itself flagged this.** Asserting that an element is NOT visible in a screenshot is inherently low-confidence. The default state of any deck without an expected list is already implicitly covered by `deck_detail_direct_navigation` (which loads Bolt Tribal, which has no expected list by default). If the section incorrectly appeared, that test would catch it.

#### 2g. `deck_detail_completeness_precon_no_expected` -- CUT

**Reason: Niche state, overlaps with existing precon intent.** `decks_precon_origin_metadata` already creates a precon and verifies its metadata display. The "(no expected list set)" guidance message is a single static string. Not worth a dedicated scenario.

#### 2h. `deck_detail_expected_import_errors` -- CUT

**Reason: Limited testability, low user impact.** The test plan correctly notes the `alert()` path is untestable via screenshots. The API error path (red text in `#expected-errors`) is testable, but requires crafting a malformed decklist that the server rejects without crashing -- fragile to maintain. The happy path is already covered by `decks_import_expected_and_completeness`.

#### 2i. `deck_detail_add_cards_search_states` -- CUT (merge into 2d)

**Reason: Redundant with approved intent 4.** The approved `deck_detail_add_cards_from_collection` already exercises the modal's initial state, typing a search query, seeing results, and selecting. Adding a separate test for "Type at least 2 characters..." and "No matching cards found" intermediate states is over-testing a search input. If the approved intent 4 verifies search works, the intermediate states are implicitly covered.

#### 2j. `deck_detail_edit_precon_fields` -- CUT

**Reason: Redundant with existing coverage.** `decks_precon_origin_metadata` already tests creating a precon with origin set, theme, and variation, and verifying those fields display correctly. Testing the checkbox toggle to show/hide precon fields is a trivial CSS interaction. If we need precon edit coverage, the approved `deck_detail_edit_properties` can optionally be run against a precon deck.

#### 2k. `deck_detail_modal_cancel_and_backdrop` -- CUT

**Reason: Low value, fragile.** Testing that Cancel buttons close modals is verifying boilerplate DOM manipulation. The test plan itself flags backdrop-click as fragile due to coordinate targeting. Every approved intent that opens a modal implicitly tests modal close behavior (save/cancel paths). No dedicated test needed.

#### 2l. `deck_detail_error_deck_not_found` -- CUT

**Reason: Trivial error state.** Navigating to `/decks/999999` and seeing "Deck not found" tests a 3-line JS error handler. Low user impact, low regression risk.

#### 2m. `deck_detail_remove_no_selection_alert` -- CUT

**Reason: Untestable.** Browser `alert()` is not captured in screenshots. The test plan correctly flagged this. The main remove flow (approved intent 2) covers the important path.

#### 2n. `deck_detail_mana_cost_rendering` -- CUT

**Reason: Implicitly covered, CDN dependency is fragile.** `deck_detail_direct_navigation` already renders the card table with mana cost columns. If mana icons render, they will be visible in that test's screenshots. A dedicated test adds nothing and introduces a CDN availability dependency.

#### 2o. `deck_detail_page_title` -- CUT

**Reason: Not screenshot-testable.** The test plan correctly identified this. Browser chrome is outside the viewport. Not worth building Playwright infrastructure to read `document.title` for a cosmetic check.

#### 2p. `deck_detail_select_all_checkbox` -- CUT (merge into 2b)

**Reason: Overlaps with approved intent 2.** The approved `deck_detail_select_and_remove_cards` can use "Select All" as its selection mechanism, testing the checkbox behavior as part of the remove flow. A separate granular checkbox test is not needed.

---

## Final Approved Intent List

| Priority | Intent Name | Covers |
|---|---|---|
| P1 | `deck_detail_zone_tab_switching` | Zone nav, active tab, counts, empty zone message |
| P1 | `deck_detail_select_and_remove_cards` | Checkbox selection (including select-all), remove, count update |
| P1 | `deck_detail_edit_properties` | Edit modal open, change name/format, save, header refresh |
| P2 | `deck_detail_add_cards_from_collection` | Add cards modal, search, select, zone choice, card appears in table |

**Total: 4 new intents** (out of 16 proposed). Combined with the 13 existing deck intents, this brings deck ecosystem coverage to 17 intents.

---

## Implementation Notes

- **Bolt Tribal (deck 1)** is the best test subject for intents 1-2: it has multi-zone cards (8 mainboard, 3 sideboard, 0 commander) verified on the container at `https://localhost:36437`.
- **Unassigned cards** for intent 4: 14 available, including "Cathar Commando" and "Infernal Vessel" which are easy search targets.
- **Intent 2 (remove cards)** should use the sideboard zone to avoid disrupting mainboard data needed by other tests, or should run last in sequence.
- **Intent 3 (edit properties)** can use either deck. Changing the name is the strongest assertion (visible in the header immediately after save).
- **Do not create intents for alert() dialogs, CSS toggle states, or CDN-dependent rendering.** These are not worth the API cost per scenario run.
