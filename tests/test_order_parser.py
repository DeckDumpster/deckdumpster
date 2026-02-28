"""
Tests for order parsing (no DB/network required).

Tests format detection, TCG text parsing, TCG HTML parsing, condition parsing.

To run: pytest tests/test_order_parser.py -v
"""

import pytest

from mtg_collector.services.order_parser import (
    detect_order_format,
    parse_order,
    _parse_condition_and_foil,
    _extract_treatment,
    _parse_dollar,
    _parse_ck_description,
)


class TestFormatDetection:
    def test_tcg_html(self):
        assert detect_order_format('<div class="orderWrap">') == "tcg_html"

    def test_tcg_html_view_source(self):
        assert detect_order_format('<span class="start-tag">div</span>') == "tcg_html"

    def test_tcg_text(self):
        assert detect_order_format("Magic\tFINAL FANTASY\tCard Name\tNear Mint") == "tcg_text"

    def test_ck_html(self):
        assert detect_order_format('<table class="table orderContents">') == "ck_html"

    def test_ck_html_cardkingdom(self):
        assert detect_order_format('<html><head><title>cardkingdom.com</title></head>') == "ck_html"

    def test_ck_text(self):
        assert detect_order_format("1x Lightning Bolt - Near Mint") == "ck_text"

    def test_ck_table_with_header(self):
        text = "Description\tStyle\tQty\tPrice\tTotal\nSecret Lair: Sol Ring (1988 - Non-Foil)\tNM\t1\t15.99\t15.99"
        assert detect_order_format(text) == "ck_text"

    def test_ck_table_without_header(self):
        """Tab-separated lines without a Description header still route to ck_text."""
        text = (
            "Marvel Eternal-Legal: Beast Within\tNM\t1\t5.99\t5.99\n"
            "Marvel Eternal-Legal: Path to Exile\tNM\t1\t5.99\t5.99\n"
        )
        assert detect_order_format(text) == "ck_text"


class TestConditionParsing:
    def test_near_mint(self):
        assert _parse_condition_and_foil("Near Mint") == ("Near Mint", False)

    def test_lightly_played(self):
        assert _parse_condition_and_foil("Lightly Played") == ("Lightly Played", False)

    def test_near_mint_foil(self):
        assert _parse_condition_and_foil("Near Mint Foil") == ("Near Mint", True)

    def test_near_mint_holofoil(self):
        assert _parse_condition_and_foil("Near Mint Holofoil") == ("Near Mint", True)

    def test_lightly_played_holofoil(self):
        assert _parse_condition_and_foil("Lightly Played Holofoil") == ("Lightly Played", True)

    def test_lightly_played_foil(self):
        assert _parse_condition_and_foil("Lightly Played Foil") == ("Lightly Played", True)


class TestTreatmentExtraction:
    def test_no_treatment(self):
        assert _extract_treatment("Lightning Bolt") == ("Lightning Bolt", None)

    def test_borderless(self):
        assert _extract_treatment("Elesh Norn (Borderless)") == ("Elesh Norn", "Borderless")

    def test_showcase(self):
        assert _extract_treatment("Fblthp (Showcase)") == ("Fblthp", "Showcase")

    def test_non_treatment_paren(self):
        # Parenthetical that isn't a known treatment stays in the name
        name, treat = _extract_treatment("Jace (Phyrexian)")
        assert treat is None
        assert "Jace" in name


class TestDollarParsing:
    def test_basic(self):
        assert _parse_dollar("$0.60") == 0.60

    def test_large(self):
        assert _parse_dollar("$1,234.56") == 1234.56

    def test_no_dollar(self):
        assert _parse_dollar("15.30") == 15.30

    def test_empty(self):
        assert _parse_dollar("") is None


class TestTcgTextParsing:
    def test_basic_line(self):
        text = "Magic - FINAL FANTASY - Jecht, Reluctant Guardian - Near Mint"
        orders = parse_order(text, "tcg_text")
        assert len(orders) == 1
        assert len(orders[0].items) == 1
        item = orders[0].items[0]
        assert item.card_name == "Jecht, Reluctant Guardian"
        assert item.set_hint == "FINAL FANTASY"
        assert item.condition == "Near Mint"
        assert item.foil is False

    def test_foil_condition(self):
        text = "Magic - Foundations - Lightning Bolt - Near Mint Foil"
        orders = parse_order(text, "tcg_text")
        item = orders[0].items[0]
        assert item.card_name == "Lightning Bolt"
        assert item.foil is True
        assert item.condition == "Near Mint"

    def test_multiple_lines(self):
        text = """Magic - FINAL FANTASY - Card One - Near Mint
Magic - FINAL FANTASY - Card Two - Lightly Played
Magic - Foundations - Card Three - Near Mint Foil"""
        orders = parse_order(text, "tcg_text")
        assert len(orders) == 1
        assert len(orders[0].items) == 3

    def test_empty_lines_ignored(self):
        text = "\nMagic - Set - Card - Near Mint\n\n"
        orders = parse_order(text, "tcg_text")
        assert len(orders) == 1
        assert len(orders[0].items) == 1

    def test_tab_separated(self):
        text = "Magic\tFINAL FANTASY\tJecht\tNear Mint"
        orders = parse_order(text, "tcg_text")
        assert len(orders) == 1
        item = orders[0].items[0]
        assert item.card_name == "Jecht"

    def test_quantity_prefix(self):
        text = "Magic - Set - 2x Lightning Bolt - Near Mint"
        orders = parse_order(text, "tcg_text")
        item = orders[0].items[0]
        assert item.quantity == 2
        assert item.card_name == "Lightning Bolt"

    def test_dual_name_card(self):
        text = "Magic - FINAL FANTASY - Aettir and Priwen - Near Mint"
        orders = parse_order(text, "tcg_text")
        item = orders[0].items[0]
        assert item.card_name == "Aettir and Priwen"

    def test_borderless_treatment(self):
        text = "Magic - Set - Elesh Norn (Borderless) - Near Mint"
        orders = parse_order(text, "tcg_text")
        item = orders[0].items[0]
        assert item.card_name == "Elesh Norn"
        assert item.treatment == "Borderless"


class TestCkTextParsing:
    def test_basic(self):
        text = "1x Lightning Bolt - Near Mint"
        orders = parse_order(text, "ck_text")
        assert len(orders) == 1
        item = orders[0].items[0]
        assert item.card_name == "Lightning Bolt"
        assert item.quantity == 1
        assert item.condition == "Near Mint"

    def test_with_set(self):
        text = "2x Counterspell [Foundations] - Lightly Played"
        orders = parse_order(text, "ck_text")
        item = orders[0].items[0]
        assert item.card_name == "Counterspell"
        assert item.set_hint == "Foundations"
        assert item.quantity == 2
        assert item.condition == "Lightly Played"

    def test_foil(self):
        text = "1x Thoughtseize - Near Mint Foil"
        orders = parse_order(text, "ck_text")
        item = orders[0].items[0]
        assert item.foil is True
        assert item.condition == "Near Mint"


class TestCkTableParsing:
    """Test CK tab-separated table format from email."""

    def test_basic_table(self):
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Marvel Eternal-Legal: Beast Within\tNM\t1\t5.99\t5.99\n"
        )
        orders = parse_order(text, "ck_text")
        assert len(orders) == 1
        item = orders[0].items[0]
        assert item.card_name == "Beast Within"
        assert item.set_hint == "Marvel Eternal-Legal"
        assert item.condition == "Near Mint"
        assert item.quantity == 1
        assert item.price == 5.99

    def test_collector_number_and_treatment(self):
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Marvel's Spider-Man Variants: Doctor Octopus, Master Planner (0228 - Borderless)\tNM\t1\t2.29\t2.29\n"
        )
        orders = parse_order(text, "ck_text")
        item = orders[0].items[0]
        assert item.card_name == "Doctor Octopus, Master Planner"
        assert item.set_hint == "Marvel's Spider-Man Variants"
        assert item.collector_number == "0228"
        assert item.treatment == "Borderless"

    def test_foil_set_name(self):
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Marvel's Spider-Man Variants Foil: Miles Morales (0234 - Borderless)\tNM\t1\t37.99\t37.99\n"
        )
        orders = parse_order(text, "ck_text")
        item = orders[0].items[0]
        assert item.card_name == "Miles Morales"
        assert item.set_hint == "Marvel's Spider-Man Variants Foil"
        assert item.foil is True
        assert item.collector_number == "0234"
        assert item.treatment == "Borderless"

    def test_non_foil_style(self):
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Secret Lair: Damnation (2019 - Non-Foil)\tNM\t1\t18.99\t18.99\n"
        )
        orders = parse_order(text, "ck_text")
        item = orders[0].items[0]
        assert item.card_name == "Damnation"
        assert item.set_hint == "Secret Lair"
        assert item.collector_number == "2019"
        assert item.foil is False

    def test_multiple_items(self):
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Marvel Eternal-Legal: Beast Within\tNM\t1\t5.99\t5.99\n"
            "Marvel Eternal-Legal: Path to Exile\tNM\t1\t5.99\t5.99\n"
            "Marvel's Spider-Man Variants: Radioactive Spider (0212 - Borderless)\tNM\t1\t0.59\t0.59\n"
        )
        orders = parse_order(text, "ck_text")
        assert len(orders[0].items) == 3
        assert orders[0].items[0].card_name == "Beast Within"
        assert orders[0].items[1].card_name == "Path to Exile"
        assert orders[0].items[2].card_name == "Radioactive Spider"
        assert orders[0].items[2].collector_number == "0212"

    def test_summary_rows_skipped(self):
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Secret Lair: Sol Ring (1988 - Non-Foil)\tNM\t1\t15.99\t15.99\n"
            "Subtotal\t\t\t\t142.95\n"
        )
        orders = parse_order(text, "ck_text")
        assert len(orders[0].items) == 1
        assert orders[0].subtotal == 142.95

    def test_auto_detect(self):
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Marvel Eternal-Legal: Beast Within\tNM\t1\t5.99\t5.99\n"
        )
        from mtg_collector.services.order_parser import detect_order_format
        assert detect_order_format(text) == "ck_text"

    def test_auto_detect_end_to_end(self):
        """Auto-detect (format=None) correctly parses CK email table."""
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Marvel Eternal-Legal: Beast Within\tNM\t1\t5.99\t5.99\n"
            "Marvel's Spider-Man Variants: Doctor Octopus, Master Planner (0228 - Borderless)\tNM\t1\t2.29\t2.29\n"
        )
        orders = parse_order(text, format=None)
        assert len(orders) == 1
        assert len(orders[0].items) == 2
        assert orders[0].items[0].card_name == "Beast Within"
        assert orders[0].items[1].card_name == "Doctor Octopus, Master Planner"
        assert orders[0].items[1].collector_number == "0228"

    def test_real_ck_email(self):
        """Full CK email order with mixed formats and summary lines."""
        text = (
            "Description\tStyle\tQty\tPrice\tTotal\n"
            "Marvel Eternal-Legal: Beast Within\tNM\t1\t5.99\t5.99\n"
            "Marvel's Spider-Man Variants: Doctor Octopus, Master Planner (0228 - Borderless)\tNM\t1\t2.29\t2.29\n"
            "Marvel Eternal-Legal: Infernal Grasp\tNM\t1\t4.49\t4.49\n"
            "Marvel's Spider-Man Variants: Kraven's Last Hunt (0226 - Borderless)\tNM\t1\t0.49\t0.49\n"
            "Marvel's Spider-Man Variants: Maximum Carnage (0225 - Borderless)\tNM\t1\t1.29\t1.29\n"
            "Marvel Eternal-Legal: Path to Exile\tNM\t1\t5.99\t5.99\n"
            "Marvel Eternal-Legal: Ponder\tNM\t1\t4.99\t4.99\n"
            "Marvel's Spider-Man Variants: Radioactive Spider (0212 - Borderless)\tNM\t1\t0.59\t0.59\n"
            "Marvel Eternal-Legal: Rest in Peace\tNM\t1\t2.29\t2.29\n"
            "Marvel Eternal-Legal: Terminate\tNM\t1\t4.99\t4.99\n"
            "Marvel's Spider-Man Variants: The Clone Saga (0219 - Borderless)\tNM\t1\t0.49\t0.49\n"
            "Marvel's Spider-Man Variants: The Death of Gwen Stacy (0223 - Borderless)\tNM\t1\t0.49\t0.49\n"
            "Subtotal\t\t\t\t34.38\n"
            "Shipping\t\t\t\t0.00\n"
            "Sales Tax\t\t\t\t3.55\n"
            "Total\t\t\t\tUSD $37.93\n"
        )
        orders = parse_order(text, "ck_text")
        assert len(orders) == 1
        order = orders[0]
        assert len(order.items) == 12
        assert order.seller_name == "Card Kingdom"

        # Spot-check items
        assert order.items[0].card_name == "Beast Within"
        assert order.items[0].set_hint == "Marvel Eternal-Legal"
        assert order.items[0].price == 5.99

        assert order.items[1].card_name == "Doctor Octopus, Master Planner"
        assert order.items[1].collector_number == "0228"
        assert order.items[1].treatment == "Borderless"

        assert order.items[3].card_name == "Kraven's Last Hunt"
        assert order.items[3].collector_number == "0226"

        # All borderless variants have treatment + collector number
        for item in order.items:
            if "Spider-Man" in (item.set_hint or ""):
                assert item.treatment == "Borderless"
                assert item.collector_number is not None

        # Financial summary
        assert order.subtotal == 34.38
        assert order.tax == 3.55
        assert order.total == 37.93


class TestTcgHtmlParsing:
    """Test TCGPlayer HTML parsing with minimal HTML snippets."""

    def _make_order_html(self, seller="Test Seller", order_number="ABC-123",
                         date="January 1, 2026", items=None, total="$10.00",
                         direct=False):
        """Build a minimal orderWrap div for testing."""
        if items is None:
            items = [{"name": "Lightning Bolt", "set": "Foundations",
                      "rarity": "C", "condition": "Near Mint", "price": "$0.10", "qty": "1"}]

        if direct:
            header_num = f'''<span style="display: inline-block; width: 20%;">
                <span class="orderTitle">TCGPLAYER DIRECT #</span><br/>
                {order_number}
            </span>'''
            seller_section = f'''<span class="orderSummary breakword">
                <span class="orderTitle">SHIPPED BY</span><br/>
                TCGplayer Direct
                <span class="orderTitle" data-aid="spn-sellerorderwidget-trackingnumber">Shipping Not Confirmed</span><br/>
                Standard (est.delivery by March 02, 2026) - $1.00
            </span>'''
        else:
            header_num = f'''<span style="display: inline-block; width: 20%;">
                <span class="orderTitle">Order Number</span><br/>
                {order_number}
            </span>'''
            seller_section = f'''<span class="orderSummary breakword">
                <span class="orderTitle">SHIPPED AND SOLD BY</span><br/>
                <span data-aid="spn-sellerorderwidget-vendorname">
                    <a class="nocontext" href="#">{seller}</a>
                </span>
                <span class="orderTitle" data-aid="spn-sellerorderwidget-trackingnumber">Shipping Not Confirmed</span><br/>
                Standard (est.delivery by March 02, 2026) - $1.00
            </span>'''

        item_rows = ""
        for i, item in enumerate(items):
            cls = "trOdd" if i % 2 == 0 else "trEven"
            item_rows += f'''<tr class="{cls}">
                <td class="orderHistoryItems">
                    <span style="display: block; padding-left: 30px;">
                        <a class="nocontext" href="#">{item["name"]}</a><br/>
                        {item["set"]}
                    </span>
                </td>
                <td class="orderHistoryDetail">Rarity: {item["rarity"]}<br/>Condition: {item["condition"]}</td>
                <td class="orderHistoryPrice">{item["price"]}</td>
                <td class="orderHistoryQuantity">{item["qty"]}</td>
            </tr>'''

        return f'''<div class="orderWrap">
            <div class="orderHeader">
                <span style="display: inline-block; width: 20%;">
                    <span class="orderTitle">Order Date</span><br/>
                    <span data-aid="spn-sellerorderwidget-orderdate">{date}</span>
                </span>
                <span style="display: inline-block; width: 20%;">
                    <span class="orderTitle">Channel</span><br/>
                    <span data-aid="spn-sellerorderwidget-orderchannel">TCG Marketplace</span>
                </span>
                {header_num}
            </div>
            <span class="orderSummary">
                <span class="orderTitle">ORDER SUMMARY</span>
                <table data-aid="tbl-sellerorderwidget-productsinorder">
                    <tr><td>Total:</td><td>{total}</td></tr>
                </table>
            </span>
            {seller_section}
            <table class="orderTable" data-aid="tbl-sellerorderwidget-ordertable">
                <thead><tr><th>ITEMS</th><th>DETAILS</th><th>PRICE</th><th>QUANTITY</th></tr></thead>
                <tbody>{item_rows}</tbody>
            </table>
        </div>'''

    def test_single_order(self):
        html = self._make_order_html()
        orders = parse_order(html, "tcg_html")
        assert len(orders) == 1
        assert orders[0].seller_name == "Test Seller"
        assert orders[0].order_number == "ABC-123"
        assert orders[0].order_date == "January 1, 2026"
        assert len(orders[0].items) == 1
        assert orders[0].items[0].card_name == "Lightning Bolt"

    def test_multi_order(self):
        html = self._make_order_html(seller="Seller A", order_number="A-1")
        html += self._make_order_html(seller="Seller B", order_number="B-2")
        orders = parse_order(html, "tcg_html")
        assert len(orders) == 2
        assert orders[0].seller_name == "Seller A"
        assert orders[1].seller_name == "Seller B"

    def test_foil_item(self):
        items = [{"name": "Card", "set": "Set", "rarity": "R",
                  "condition": "Near Mint Foil", "price": "$1.00", "qty": "1"}]
        html = self._make_order_html(items=items)
        orders = parse_order(html, "tcg_html")
        assert orders[0].items[0].foil is True
        assert orders[0].items[0].condition == "Near Mint"

    def test_holofoil_item(self):
        items = [{"name": "Card", "set": "Set", "rarity": "M",
                  "condition": "Near Mint Holofoil", "price": "$5.00", "qty": "1"}]
        html = self._make_order_html(items=items)
        orders = parse_order(html, "tcg_html")
        assert orders[0].items[0].foil is True

    def test_quantity_gt_1(self):
        items = [{"name": "Card", "set": "Set", "rarity": "C",
                  "condition": "Near Mint", "price": "$0.05", "qty": "3"}]
        html = self._make_order_html(items=items)
        orders = parse_order(html, "tcg_html")
        assert orders[0].items[0].quantity == 3

    def test_multiple_items(self):
        items = [
            {"name": "Card A", "set": "Set", "rarity": "C", "condition": "Near Mint", "price": "$0.05", "qty": "1"},
            {"name": "Card B", "set": "Set", "rarity": "R", "condition": "Lightly Played", "price": "$1.00", "qty": "2"},
        ]
        html = self._make_order_html(items=items)
        orders = parse_order(html, "tcg_html")
        assert len(orders[0].items) == 2
        assert orders[0].items[0].card_name == "Card A"
        assert orders[0].items[1].card_name == "Card B"
        assert orders[0].items[1].condition == "Lightly Played"

    def test_direct_order(self):
        html = self._make_order_html(direct=True, order_number="260214-3ADF")
        orders = parse_order(html, "tcg_html")
        assert len(orders) == 1
        assert orders[0].seller_name == "TCGplayer Direct"
        assert orders[0].order_number == "260214-3ADF"

    def test_estimated_delivery(self):
        html = self._make_order_html()
        orders = parse_order(html, "tcg_html")
        assert orders[0].estimated_delivery == "March 02, 2026"

    def test_financial_total(self):
        html = self._make_order_html(total="$25.99")
        orders = parse_order(html, "tcg_html")
        assert orders[0].total == 25.99

    def test_rarity_hint(self):
        items = [{"name": "Card", "set": "Set", "rarity": "ACE SPEC Rare",
                  "condition": "Near Mint", "price": "$1.00", "qty": "1"}]
        html = self._make_order_html(items=items)
        orders = parse_order(html, "tcg_html")
        assert orders[0].items[0].rarity_hint == "ACE SPEC Rare"


class TestCkDescriptionParsing:
    def test_simple(self):
        name, set_hint, treatment, cn = _parse_ck_description("Lightning Bolt: Foundations")
        assert name == "Lightning Bolt"
        assert set_hint == "Foundations"
        assert treatment is None
        assert cn is None

    def test_with_treatment_and_cn(self):
        name, set_hint, treatment, cn = _parse_ck_description(
            "Aerith Gainsborough (0374 - Borderless): Final Fantasy Variants"
        )
        assert name == "Aerith Gainsborough"
        assert set_hint == "Final Fantasy Variants"
        assert treatment == "Borderless"
        assert cn == "0374"

    def test_no_colon(self):
        name, set_hint, treatment, cn = _parse_ck_description("Lightning Bolt")
        assert name == "Lightning Bolt"
        assert set_hint is None
        assert treatment is None
        assert cn is None

    def test_collector_number_only(self):
        name, set_hint, treatment, cn = _parse_ck_description(
            "Sol Ring (0123): Commander Masters"
        )
        assert name == "Sol Ring"
        assert set_hint == "Commander Masters"
        assert treatment is None
        assert cn == "0123"

    def test_set_with_colon(self):
        name, set_hint, treatment, cn = _parse_ck_description(
            "Sol Ring (Commander Collection - Foil Etched): Commander Collection: Green"
        )
        assert name == "Sol Ring"
        assert set_hint == "Commander Collection: Green"
        assert treatment == "Foil Etched"
        assert cn is None

    def test_treatment_only_no_cn(self):
        name, set_hint, treatment, cn = _parse_ck_description(
            "Herald's Horn (Buy-a-Box Foil): Promotional"
        )
        assert name == "Herald's Horn"
        assert set_hint == "Promotional"
        assert treatment == "Buy-a-Box Foil"
        assert cn is None


class TestCkHtmlParsing:
    """Test Card Kingdom HTML parsing with minimal HTML snippets."""

    def _make_ck_html(self, order_number="161969019", items=None,
                       subtotal="$69.20", shipping="$0.00", tax="$7.12",
                       total="$76.32", condition_group="NM"):
        """Build a minimal CK invoice HTML for testing."""
        if items is None:
            items = [
                {"desc": "Lightning Bolt: Foundations", "condition": "NM",
                 "qty": "1", "price": "$0.25", "total": "$0.25"},
            ]

        item_rows = ""
        for item in items:
            item_rows += f'''<tr valign=top>
                <td class="Description">{item["desc"]}</td>
                <td align=center>{item["condition"]}</td>
                <td align=center>{item["qty"]}</td>
                <td align=right>{item["price"]}</td>
                <td align=right>{item["total"]}</td>
            </tr>'''

        return f'''<html>
        <body>
        <h1>My Account / Order #{order_number}</h1>
        <table class="table orderContents">
            <tr><td colspan=5><h3>{condition_group} SINGLES</h3></td></tr>
            <tr>
                <th>Description</th><th>Style</th><th>Qty</th><th>Price</th><th>Total</th>
            </tr>
            {item_rows}
            <tr>
                <td>Subtotal</td><td></td><td></td><td></td><td align=right>{subtotal}</td>
            </tr>
            <tr>
                <td>Shipping</td><td></td><td></td><td></td><td align=right>{shipping}</td>
            </tr>
            <tr>
                <td>Sales Tax</td><td></td><td></td><td></td><td align=right>{tax}</td>
            </tr>
            <tr>
                <td>Total</td><td></td><td></td><td></td><td align=right>{total}</td>
            </tr>
        </table>
        </body></html>'''

    def test_single_item(self):
        html = self._make_ck_html()
        orders = parse_order(html, "ck_html")
        assert len(orders) == 1
        assert orders[0].order_number == "161969019"
        assert orders[0].seller_name == "Card Kingdom"
        assert orders[0].source == "cardkingdom"
        assert len(orders[0].items) == 1
        item = orders[0].items[0]
        assert item.card_name == "Lightning Bolt"
        assert item.set_hint == "Foundations"
        assert item.condition == "Near Mint"
        assert item.quantity == 1
        assert item.price == 0.25

    def test_financial_summary(self):
        html = self._make_ck_html()
        orders = parse_order(html, "ck_html")
        assert orders[0].subtotal == 69.20
        assert orders[0].shipping == 0.00
        assert orders[0].tax == 7.12
        assert orders[0].total == 76.32

    def test_multiple_items(self):
        items = [
            {"desc": "Lightning Bolt: Foundations", "condition": "NM",
             "qty": "1", "price": "$0.25", "total": "$0.25"},
            {"desc": "Counterspell: Masters 25", "condition": "NM",
             "qty": "2", "price": "$1.50", "total": "$3.00"},
        ]
        html = self._make_ck_html(items=items)
        orders = parse_order(html, "ck_html")
        assert len(orders[0].items) == 2
        assert orders[0].items[0].card_name == "Lightning Bolt"
        assert orders[0].items[1].card_name == "Counterspell"
        assert orders[0].items[1].quantity == 2

    def test_borderless_treatment(self):
        items = [
            {"desc": "Aerith Gainsborough (0374 - Borderless): Final Fantasy Variants",
             "condition": "NM", "qty": "1", "price": "$8.99", "total": "$8.99"},
        ]
        html = self._make_ck_html(items=items)
        orders = parse_order(html, "ck_html")
        item = orders[0].items[0]
        assert item.card_name == "Aerith Gainsborough"
        assert item.set_hint == "Final Fantasy Variants"
        assert item.treatment == "Borderless"
        assert item.collector_number == "0374"

    def test_header_row_skipped(self):
        """Column header text like 'Description' should not be parsed as a card."""
        html = '''<html><body>
        <h1>My Account / Order #999</h1>
        <table class="table orderContents">
            <tr><td>Description</td><td>Style</td><td>Qty</td><td>Price</td><td>Total</td></tr>
            <tr valign=top>
                <td class="Description">Lightning Bolt: Foundations</td>
                <td align=center>NM</td>
                <td align=center>1</td>
                <td align=right>$0.25</td>
                <td align=right>$0.25</td>
            </tr>
        </table></body></html>'''
        orders = parse_order(html, "ck_html")
        assert len(orders[0].items) == 1
        assert orders[0].items[0].card_name == "Lightning Bolt"

    def test_lp_condition_group(self):
        items = [
            {"desc": "Sol Ring: Commander Masters", "condition": "LP",
             "qty": "1", "price": "$1.00", "total": "$1.00"},
        ]
        html = self._make_ck_html(items=items, condition_group="LP")
        orders = parse_order(html, "ck_html")
        item = orders[0].items[0]
        assert item.condition == "Lightly Played"

    def test_foil_section(self):
        html = '''<html><body>
        <h1>My Account / Order #999</h1>
        <table class="table orderContents">
            <tr><td colspan=5><h3>NM FOILS</h3></td></tr>
            <tr><th>Description</th><th>Style</th><th>Qty</th><th>Price</th><th>Total</th></tr>
            <tr valign=top>
                <td class="Description">Lightning Bolt: Foundations</td>
                <td align=center>NM</td>
                <td align=center>1</td>
                <td align=right>$2.00</td>
                <td align=right>$2.00</td>
            </tr>
        </table></body></html>'''
        orders = parse_order(html, "ck_html")
        assert orders[0].items[0].foil is True

    def test_auto_detect(self):
        html = self._make_ck_html()
        orders = parse_order(html)
        assert len(orders) == 1
        assert orders[0].source == "cardkingdom"

    def test_html_entities(self):
        items = [
            {"desc": "Aerith&#039;s Garden: Final Fantasy", "condition": "NM",
             "qty": "1", "price": "$1.00", "total": "$1.00"},
        ]
        html = self._make_ck_html(items=items)
        orders = parse_order(html, "ck_html")
        assert orders[0].items[0].card_name == "Aerith's Garden"

    def test_view_source_wrapper(self):
        """Firefox view-source wraps each line in <span id='lineN'> with HTML as text."""
        from html import escape
        inner = self._make_ck_html()
        # Firefox view-source escapes the HTML and wraps in span lines
        wrapped_lines = []
        for i, line in enumerate(inner.splitlines(), 1):
            wrapped_lines.append(f'<span id="line{i}">{escape(line)}</span>')
        html = "<html><body>" + "\n".join(wrapped_lines) + "</body></html>"
        orders = parse_order(html, "ck_html")
        assert len(orders) == 1
        assert orders[0].items[0].card_name == "Lightning Bolt"


class TestRealCkHtml:
    """Test parsing real Card Kingdom HTML files if available."""

    @pytest.fixture
    def real_html(self):
        import os
        path = os.path.expanduser("~/Downloads/ck-order-example.html")
        if not os.path.exists(path):
            pytest.skip("Real CK HTML file not available")
        with open(path) as f:
            return f.read()

    def test_parses_items(self, real_html):
        orders = parse_order(real_html, "ck_html")
        assert len(orders) >= 1
        assert len(orders[0].items) > 0

    def test_all_items_have_names(self, real_html):
        orders = parse_order(real_html, "ck_html")
        for o in orders:
            for item in o.items:
                assert item.card_name, "Item missing card name"


class TestRealTcgHtml:
    """Test parsing the real TCGPlayer order HTML files if available."""

    @pytest.fixture
    def real_html(self):
        import os
        files = [
            os.path.expanduser("~/Downloads/order-page-example-1.html"),
            os.path.expanduser("~/Downloads/order-page-example-2.html"),
        ]
        if not all(os.path.exists(f) for f in files):
            pytest.skip("Real TCGPlayer HTML files not available")
        text = ""
        for f in files:
            with open(f) as fh:
                text += fh.read()
        return text

    def test_parses_all_orders(self, real_html):
        orders = parse_order(real_html, "tcg_html")
        assert len(orders) == 20

    def test_total_items(self, real_html):
        orders = parse_order(real_html, "tcg_html")
        total = sum(len(o.items) for o in orders)
        assert total == 120

    def test_all_orders_have_seller(self, real_html):
        orders = parse_order(real_html, "tcg_html")
        for o in orders:
            assert o.seller_name, f"Order {o.order_number} missing seller name"

    def test_all_orders_have_number(self, real_html):
        orders = parse_order(real_html, "tcg_html")
        for o in orders:
            assert o.order_number, f"Order from {o.seller_name} missing order number"

    def test_items_have_names(self, real_html):
        orders = parse_order(real_html, "tcg_html")
        for o in orders:
            for item in o.items:
                assert item.card_name, f"Item in order {o.order_number} missing card name"
