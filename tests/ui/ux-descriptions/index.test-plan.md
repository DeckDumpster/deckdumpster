# Homepage (`/`) -- Test Plan

Source: `tests/ui/ux-descriptions/index.md`

## Existing Coverage

The following existing intent already covers a homepage scenario:

- **`batches_homepage_nav_link`** -- Navigates from the homepage Collection group to the Batches page. Covers the "Batches" link specifically.

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### homepage_page_structure
- **Description**: When I visit the homepage, I can see three navigation groups labeled "Collection", "Analysis", and "Add Cards", each containing their respective links with subtitle descriptions. The page title and overall layout render correctly.
- **References**: UX Description SS Page Purpose, SS Navigation (all three groups), SS Visual States (State 1, State 2)
- **Testability**: full
- **Priority**: high

### homepage_collection_nav_links
- **Description**: I can see all five links in the Collection navigation group (Cards, Decks, Binders, Sealed, Batches) with their subtitle descriptions, and clicking each one navigates to the correct destination page.
- **References**: UX Description SS Navigation > Collection Group
- **Testability**: full
- **Priority**: high

### homepage_analysis_nav_links
- **Description**: I can see all three links in the Analysis navigation group (Crack-a-Pack, Explore Sheets, Set Value) with their subtitle descriptions, and clicking each one navigates to the correct destination page.
- **References**: UX Description SS Navigation > Analysis Group
- **Testability**: full
- **Priority**: high

### homepage_add_cards_nav_links
- **Description**: I can see all six links in the Add Cards navigation group (Upload, Recent, Corners, Manual ID, Orders, CSV Import) with their subtitle descriptions, and clicking each one navigates to the correct destination page. The Upload and Recent links appear inside an "OCR" subgroup.
- **References**: UX Description SS Navigation > Add Cards Group
- **Testability**: full
- **Priority**: high

### homepage_image_display_setting
- **Description**: When I visit the homepage and scroll to the Settings section, I can see the "Image Display" pills (Crop and Contain). One pill is active based on the saved setting. When I click the inactive pill, it becomes active (red background), the previously active pill deactivates, and a green "Saved" indicator briefly appears.
- **References**: UX Description SS Interactive Elements > Image Display Pills, SS User Flows > Flow 2, SS Dynamic Behavior > On Setting Change
- **Testability**: full
- **Priority**: high

### homepage_price_source_setting
- **Description**: When I visit the homepage and scroll to the Settings section, I can see the "Price Sources" pills (TCG and CK). I can toggle each pill independently -- clicking an active pill deactivates it, clicking an inactive pill activates it. After each toggle, a green "Saved" indicator briefly appears. Both pills can be active, one, or neither.
- **References**: UX Description SS Interactive Elements > Price Source Checks, SS User Flows > Flow 3, SS Dynamic Behavior > On Setting Change
- **Testability**: full
- **Priority**: high

### homepage_settings_load_on_page_open
- **Description**: When I first load the homepage, the settings pills initially appear without any active state. After the page finishes loading (fetching GET /api/settings), the correct pills become active to reflect the saved configuration. This confirms that `loadSettings()` runs on page load and applies the response to the UI.
- **References**: UX Description SS Dynamic Behavior > On Page Load (loadSettings), SS Visual States (State 1 vs State 2)
- **Testability**: full
- **Priority**: medium

### homepage_save_status_indicator
- **Description**: When I change a setting on the homepage (either Image Display or Price Sources), the green "Saved" text fades in and then automatically fades out after approximately 1.5 seconds. The text is invisible before any setting change.
- **References**: UX Description SS Interactive Elements > Save Status Indicator, SS Dynamic Behavior > On Setting Change
- **Testability**: full
- **Priority**: medium

### homepage_recent_badge_processing
- **Description**: When there are cards in the OCR processing pipeline (READY_FOR_OCR or PROCESSING status), the homepage displays a red badge next to the "Recent" link showing the count and the word "processing". Clicking the "Recent" link navigates to the processing queue.
- **References**: UX Description SS User Flows > Flow 4, SS Dynamic Behavior > On Page Load (loadIngestCounts), SS Visual States (State 3)
- **Testability**: limited (requires ingest pipeline data in READY_FOR_OCR or PROCESSING state; test fixture may not include this data, so the badge may not appear without seeding the database)
- **Priority**: medium

### homepage_recent_badge_absent_when_idle
- **Description**: When there are no cards currently being processed in the OCR pipeline, the homepage does not show any badge next to the "Recent" link. The badge wrapper element exists in the DOM but contains no content.
- **References**: UX Description SS Dynamic Behavior > On Page Load (loadIngestCounts), SS Visual States (State 2)
- **Testability**: full
- **Priority**: medium

### homepage_nav_link_hover_styling
- **Description**: When I hover over a navigation link on the homepage, the link's border turns red and the background lightens, providing visual feedback that the link is interactive.
- **References**: UX Description SS Interactive Elements > Navigation Links
- **Testability**: full
- **Priority**: low

### homepage_mobile_responsive_layout
- **Description**: When I view the homepage on a narrow viewport (768px or less), the three navigation groups stack vertically instead of appearing side-by-side, and each group expands to full width. The settings section remains unchanged.
- **References**: UX Description SS Visual States > State 7 (Mobile / Narrow Viewport)
- **Testability**: full
- **Priority**: medium

### homepage_ocr_subgroup_label
- **Description**: Within the Add Cards navigation group, the Upload and Recent links appear under a visible "OCR" sub-label inside a distinct subgroup container, visually separating them from the other Add Cards links (Corners, Manual ID, Orders, CSV Import).
- **References**: UX Description SS Navigation > Add Cards Group > OCR Subgroup
- **Testability**: full
- **Priority**: low

### homepage_settings_api_failure_graceful
- **Description**: When the settings API endpoint fails or returns an error, the homepage still renders all navigation links and remains fully navigable. The settings pills appear without any active state (all gray), but clicking them still attempts to save.
- **References**: UX Description SS Visual States > State 5 (API Failure - Settings)
- **Testability**: limited (requires intercepting or mocking the /api/settings endpoint to simulate failure; Playwright can do route interception, but this goes beyond standard test fixture capabilities)
- **Priority**: low

### homepage_no_persistent_header
- **Description**: The homepage does not display a persistent header navigation bar, back link, or breadcrumb. It serves as the top-level entry point of the application with no upward navigation.
- **References**: UX Description SS Navigation > Other Links (final paragraph)
- **Testability**: full
- **Priority**: low

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| Page Purpose | `homepage_page_structure` |
| Navigation > Collection Group | `homepage_collection_nav_links`, `batches_homepage_nav_link` (existing) |
| Navigation > Analysis Group | `homepage_analysis_nav_links` |
| Navigation > Add Cards Group | `homepage_add_cards_nav_links`, `homepage_ocr_subgroup_label` |
| Navigation > Other Links | `homepage_no_persistent_header` |
| Interactive Elements > Image Display Pills | `homepage_image_display_setting` |
| Interactive Elements > Price Source Checks | `homepage_price_source_setting` |
| Interactive Elements > Save Status Indicator | `homepage_save_status_indicator` |
| Interactive Elements > Navigation Links (hover) | `homepage_nav_link_hover_styling` |
| User Flow 1: Navigate to Feature Page | `homepage_collection_nav_links`, `homepage_analysis_nav_links`, `homepage_add_cards_nav_links` |
| User Flow 2: Change Image Display Mode | `homepage_image_display_setting` |
| User Flow 3: Toggle Price Sources | `homepage_price_source_setting` |
| User Flow 4: Check OCR Processing Status | `homepage_recent_badge_processing`, `homepage_recent_badge_absent_when_idle` |
| Dynamic Behavior > On Page Load | `homepage_settings_load_on_page_open`, `homepage_recent_badge_processing`, `homepage_recent_badge_absent_when_idle` |
| Dynamic Behavior > On Setting Change | `homepage_image_display_setting`, `homepage_price_source_setting`, `homepage_save_status_indicator` |
| Visual States > State 1 (Pre-JS) | `homepage_settings_load_on_page_open` |
| Visual States > State 2 (Fully Loaded, No Processing) | `homepage_page_structure`, `homepage_recent_badge_absent_when_idle` |
| Visual States > State 3 (With Processing Items) | `homepage_recent_badge_processing` |
| Visual States > State 4 (Setting Just Saved) | `homepage_save_status_indicator` |
| Visual States > State 5 (API Failure - Settings) | `homepage_settings_api_failure_graceful` |
| Visual States > State 6 (API Failure - Ingest Counts) | `homepage_recent_badge_absent_when_idle` (partial -- same visual result) |
| Visual States > State 7 (Mobile) | `homepage_mobile_responsive_layout` |

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 5 | `homepage_page_structure`, `homepage_collection_nav_links`, `homepage_analysis_nav_links`, `homepage_add_cards_nav_links`, `homepage_image_display_setting`, `homepage_price_source_setting` |
| Medium | 5 | `homepage_settings_load_on_page_open`, `homepage_save_status_indicator`, `homepage_recent_badge_processing`, `homepage_recent_badge_absent_when_idle`, `homepage_mobile_responsive_layout` |
| Low | 4 | `homepage_nav_link_hover_styling`, `homepage_ocr_subgroup_label`, `homepage_settings_api_failure_graceful`, `homepage_no_persistent_header` |

**Total new intents: 14** (plus 1 existing: `batches_homepage_nav_link`)
