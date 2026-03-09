# Index Page — Approved Intents

## Implement Now

- `homepage_page_structure` — When I visit the homepage, I can see three navigation groups labeled "Collection", "Analysis", and "Add Cards", each containing their expected links with subtitle descriptions, and a Settings section below.

- `homepage_nav_links_collection` — When I click each link in the Collection group (Cards, Decks, Binders, Sealed), the browser navigates to the correct destination page. (Batches is excluded -- already covered by `batches_homepage_nav_link`.)

- `homepage_nav_links_analysis_and_addcards` — When I click each link in the Analysis group (Crack-a-Pack, Explore Sheets, Set Value) and the Add Cards group (Upload, Recent, Corners, Manual ID, Orders, CSV Import), each navigates to the correct destination page. The OCR subgroup with its "OCR" sub-label is visible containing Upload and Recent.

- `homepage_image_display_setting` — When I visit the homepage, the Image Display pills reflect the saved setting (one pill active). When I click the inactive pill, it becomes active, the other deactivates, and the green "Saved" indicator briefly appears. Refreshing the page confirms the new setting persisted.

- `homepage_price_source_setting` — When I visit the homepage, the Price Sources pills reflect the saved setting. I can toggle each pill independently (both active, one, or neither). After each toggle, the "Saved" indicator appears and the change persists across page reload.

- `homepage_recent_badge_absent_when_idle` — When no cards are in READY_FOR_OCR or PROCESSING state, the homepage does not show a processing badge next to the "Recent" link. The link is still visible and navigable.

## Deferred

- `homepage_collection_nav_links` (original) — Merged into `homepage_nav_links_collection`. The original tested all five Collection links including Batches, which is already covered by `batches_homepage_nav_link`.

- `homepage_analysis_nav_links` (original) — Merged into `homepage_nav_links_analysis_and_addcards`. Testing Analysis and Add Cards navigation separately provides no additional regression value since the mechanism is identical (anchor hrefs).

- `homepage_add_cards_nav_links` (original) — Merged into `homepage_nav_links_analysis_and_addcards`. Same rationale.

- `homepage_ocr_subgroup_label` — Merged into `homepage_nav_links_analysis_and_addcards`. The OCR sub-label is verified as part of walking the Add Cards group. Does not need its own intent.

- `homepage_settings_load_on_page_open` — Redundant with `homepage_image_display_setting` and `homepage_price_source_setting`. Both already verify that pills reflect saved state on page load. Testing the pre-JS "all gray" transient state is unreliable with Playwright since the settings API responds in single-digit milliseconds on localhost.

- `homepage_save_status_indicator` — Redundant. The "Saved" indicator appearance is already verified as part of both settings intents. A standalone test for a 1.5s CSS opacity transition adds no regression value.

- `homepage_recent_badge_processing` — Not testable with current fixture data. The test container returns `{"DONE": 2, "ERROR": 2}` with zero READY_FOR_OCR or PROCESSING entries. The badge requires seeding the ingest pipeline with specific statuses, which the `--test` fixture does not support. Revisit when fixture tooling supports ingest pipeline state injection.

- `homepage_nav_link_hover_styling` — Low value. Hover effects are pure CSS (`:hover` pseudo-class). Claude Vision cannot reliably verify hover state rendering. Playwright could assert computed styles, but this tests the browser's CSS engine, not application logic.

- `homepage_mobile_responsive_layout` — Deferred. Responsive layout is pure CSS (`@media max-width: 768px`). While Playwright can set viewport size, verifying "groups stack vertically" via Claude Vision screenshot comparison is fragile and low regression value for a media query that is unlikely to regress independently.

- `homepage_settings_api_failure_graceful` — Not testable without Playwright route interception to mock API failures. This goes beyond the standard intent/hint/implementation pattern which operates against a real running server. The failure mode is also trivially simple (no pills active, page still navigable).

- `homepage_no_persistent_header` — Trivially true and not a regression risk. The homepage has never had a persistent header. Asserting the absence of something that was never there provides zero regression value.
