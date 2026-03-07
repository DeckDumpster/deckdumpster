"""
Hand-written implementation for card_detail_direct_navigation.

Navigates directly to /card/blb/124 and verifies core card detail rendering:
card name, type, set info, external links, and site header.
"""


def steps(harness):
    # start_page: /card/blb/124 — auto-navigated by test runner.
    # Card name heading.
    harness.wait_for_text("Artist's Talent")
    harness.assert_text_present("Artist's Talent")
    # Type line.
    harness.assert_text_present("Enchantment")
    # Set info.
    harness.assert_text_present("Bloomburrow")
    # Rarity.
    harness.assert_text_present("Rare")
    # Artist.
    harness.assert_text_present("Lars Grant-West")
    # External link badges (SF and CK).
    harness.assert_visible("a.badge.link")
    # Site header nav.
    harness.assert_visible(".site-header")
    harness.assert_text_present("Collection")
    harness.assert_text_present("Decks")
    harness.screenshot("final_state")
