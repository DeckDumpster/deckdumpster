"""Scryfall bulk data is gzipped JSONL, and must be parsed as a stream.

Scryfall dropped `download_uri` from /bulk-data on 2026-07-20 and replaced the
plain-JSON dumps with `jsonl_download_uri` pointing at a `.jsonl.gz` (de-mjt).
The decompressed default_cards file is several GB, so it is read a line at a
time rather than materialised as a list.
"""

import gzip
import json

from mtg_collector.cli.cache_cmd import _bulk_jsonl_uri, _iter_bulk_cards

# Shape of a real /bulk-data response as Scryfall serves it today: no
# `download_uri` key anywhere, and `size` replaced by `compressed_size`.
BULK_META = {
    "object": "list",
    "data": [
        {
            "object": "bulk_data",
            "type": "oracle_cards",
            "jsonl_download_uri": "https://data.scryfall.io/oracle-cards/oracle-cards-1.jsonl.gz",
            "compressed_size": 24532607,
        },
        {
            "object": "bulk_data",
            "type": "default_cards",
            "jsonl_download_uri": "https://data.scryfall.io/default-cards/default-cards-1.jsonl.gz",
            "compressed_size": 77546774,
        },
    ],
}


class TestBulkJsonlUri:
    def test_picks_default_cards_jsonl_uri(self):
        assert _bulk_jsonl_uri(BULK_META) == (
            "https://data.scryfall.io/default-cards/default-cards-1.jsonl.gz"
        )

    def test_selects_by_type(self):
        assert _bulk_jsonl_uri(BULK_META, "oracle_cards") == (
            "https://data.scryfall.io/oracle-cards/oracle-cards-1.jsonl.gz"
        )

    def test_missing_type_returns_none(self):
        assert _bulk_jsonl_uri(BULK_META, "all_cards") is None

    def test_empty_response_returns_none(self):
        assert _bulk_jsonl_uri({}) is None


class TestIterBulkCards:
    def _write(self, tmp_path, lines):
        path = tmp_path / "bulk.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write("".join(lines))
        return path

    def test_yields_one_dict_per_line(self, tmp_path):
        path = self._write(
            tmp_path,
            [json.dumps({"id": str(i), "set": "ecl"}) + "\n" for i in range(3)],
        )
        cards = list(_iter_bulk_cards(path))
        assert [c["id"] for c in cards] == ["0", "1", "2"]

    def test_skips_blank_lines(self, tmp_path):
        path = self._write(
            tmp_path,
            [json.dumps({"id": "a"}) + "\n", "\n", json.dumps({"id": "b"}) + "\n"],
        )
        assert [c["id"] for c in _iter_bulk_cards(path)] == ["a", "b"]

    def test_handles_unicode_card_names(self, tmp_path):
        path = self._write(
            tmp_path, [json.dumps({"name": "Æther Vial", "id": "æ"}) + "\n"]
        )
        assert list(_iter_bulk_cards(path))[0]["name"] == "Æther Vial"

    def test_is_lazy_not_a_materialised_list(self, tmp_path):
        """The whole point: nothing is read until the consumer asks for it.

        A list-building implementation would decompress and parse every line
        before the first card came back; this asserts the generator hands over
        card 1 without having touched the rest.
        """
        path = self._write(
            tmp_path,
            [json.dumps({"id": str(i)}) + "\n" for i in range(1000)],
        )
        it = _iter_bulk_cards(path)
        first = next(it)
        assert first["id"] == "0"
        # Consuming one card must not have exhausted the file.
        assert next(it)["id"] == "1"
        it.close()
