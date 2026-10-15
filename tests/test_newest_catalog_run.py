"""derive reads the newest run that landed every catalogue input, not the newest run."""

import json

import pytest

from mtg_collector.landing import CATALOG_DATASETS, ReplayMiss, newest_catalog_run


def _land(root, run, source, dataset, entries=1):
    d = root / f"source={source}" / f"dataset={dataset}" / "ingest_date=2026-10-14" / f"run={run}"
    d.mkdir(parents=True)
    (d / "_manifest.json").write_text(json.dumps({
        "run_id": run, "source": source, "dataset": dataset, "ingest_date": "2026-10-14",
        "entries": [{"url": "u", "object": "o"}] * entries}))


def test_a_later_edhrec_or_price_run_is_not_the_catalogue(tmp_path):
    for s, d in CATALOG_DATASETS:
        _land(tmp_path, "01", s, d)
    _land(tmp_path, "02", "edhrec", "commanders")
    _land(tmp_path, "03", "tcgcsv", "prices")
    assert newest_catalog_run(tmp_path) == "01"


def test_a_partial_catalogue_run_is_skipped(tmp_path):
    for s, d in CATALOG_DATASETS:
        _land(tmp_path, "01", s, d)
    for s, d in sorted(CATALOG_DATASETS)[:-1]:
        _land(tmp_path, "02", s, d)
    assert newest_catalog_run(tmp_path) == "01"


def test_no_complete_run_is_a_miss_not_a_guess(tmp_path):
    _land(tmp_path, "01", "edhrec", "commanders")
    with pytest.raises(ReplayMiss):
        newest_catalog_run(tmp_path)
