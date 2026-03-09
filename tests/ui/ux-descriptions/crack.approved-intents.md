# Crack-a-Pack -- Approved Intents

Reviewed: 2026-03-09
Existing intents: 3 (`crack_pack_normal_mode`, `crack_pack_surprise_mode`, `crack_pack_pick_cards`)
Proposed new: 19
Result: 8 approved for implementation, 4 deferred, 7 cut

Container note: The `/api/generate` endpoint returns empty responses in the
`--test` fixture container. All intents that require opening a pack depend on
this being fixed or on using a `--init` container with full seed data. If the
endpoint remains broken under `--test`, the only immediately runnable intent
is `crack_pack_initial_empty_state`.

---

## Implement Now

- `crack_pack_initial_empty_state` -- Load `/crack` and verify all disabled-state elements: set input shows "Search sets..." after load, Open Pack / Reveal All / Explore Sheets buttons are disabled, pack header reads "Select a set and open a pack", picks panel shows "(0)" and placeholder text. This is the single highest-value new intent because it validates page load correctness with zero API interaction beyond `/api/sets`.

- `crack_pack_set_search_filter` -- Type a partial set name into the search input, verify the dropdown opens and filters in real time, use keyboard arrows + Enter to select a set, confirm input shows "Name (code)" and dropdown closes. Merge the proposed `crack_pack_set_search_reselect` into this: after selection, click back into the input and confirm it clears and reopens the dropdown. This tests the core prerequisite flow for everything else on the page.

- `crack_pack_product_selection` -- After selecting a set, verify product radio pills appear with the first auto-selected (red background), confirm Open Pack and Explore Sheets buttons become enabled, switch to a different product pill and verify the highlight moves. Small and self-contained.

- `crack_pack_unpick_card` -- Open a pack in normal mode, pick a card, then click the same card again. Verify the red glow and PICKED badge are removed, the card is removed from the picks panel, and the count decreases. This covers the pick toggle path not exercised by the existing `crack_pack_pick_cards`.

- `crack_pack_clear_all_picks` -- Open a pack, pick several cards, click "Clear All". Verify picks panel returns to empty state ("Click cards to pick them"), count shows "(0)", and all PICKED overlays in the grid are removed. Tests bulk pick management.

- `crack_pack_zoom_card` -- Open a pack in normal mode, click a zoom badge. Verify the full-screen overlay appears with a large card image. Click the overlay to dismiss. Verify the zoom click did NOT toggle the card's pick state. Tests overlay open/close and event isolation.

- `crack_pack_url_hash_share` -- Open a pack, capture the URL hash, reload the page with that hash, and verify the same pack is deterministically regenerated with matching cards. This is a high-value regression test for the sharing feature. Subsumes the proposed `crack_pack_url_hash_partial_reveal` -- partial reveal can be checked as a sub-step within this single intent.

- `crack_pack_sequential_packs` -- Open a pack, pick some cards, open a second pack. Verify the grid replaces, picks from the first pack persist in the sidebar, and PICKED styling does not incorrectly appear on the new pack's cards. Tests pick persistence and state isolation.

## Deferred

- `crack_pack_reveal_individual_cards` -- The existing `crack_pack_surprise_mode` already covers individual reveal and Reveal All. A dedicated deeper test adds marginal value. Defer unless surprise_mode coverage proves insufficient in practice.

- `crack_pack_grid_columns` -- Column adjustment is a low-interaction visual control. Defer. The localStorage persistence aspect also requires page reload support in the harness.

- `crack_pack_navigate_explore_sheets` -- Simple navigation test (verify the button navigates to `/sheets#set=X&product=Y`). Low regression risk. Defer.

- `crack_pack_ck_prices_update` -- Network-dependent (fetches from external Card Kingdom API). The test fixture shows CK as "unavailable". Untestable in `--test` mode. Defer.

## Cut

- `crack_pack_set_search_reselect` -- Merged into `crack_pack_set_search_filter`. No standalone intent needed.
- `crack_pack_remove_pick_from_panel` -- Redundant with `crack_pack_unpick_card` (both test removing a pick, just via different click targets). The grid-click removal covers the core logic; the panel "x" button is a minor UI variation.
- `crack_pack_url_hash_partial_reveal` -- Merged into `crack_pack_url_hash_share` as a sub-step.
- `crack_pack_header_home_link` -- Trivial navigation link. Zero regression value.
- `crack_pack_pack_header_stats` -- The pack header format is already implicitly verified by any intent that opens a pack. No dedicated intent needed.
- `crack_pack_card_badges` -- Badge rendering depends on fixture data having specific treatments. Partially covered by the existing `crack_pack_normal_mode` which already checks for "treatment badges". Low incremental value.
- `crack_pack_foil_visual_effects` -- CSS animation effects cannot be reliably asserted via screenshots. Untestable.
