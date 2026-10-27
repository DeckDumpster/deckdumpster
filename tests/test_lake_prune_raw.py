"""A synced run's raw objects are pruned from the local lake; an unsynced run's are kept (sp-ol9a3q)."""

import json

from mtg_collector.lake import prune_raw

CAT = [("scryfall", "default_cards"), ("mtgjson", "allprintings"), ("mtgjson", "meta")]


def land(root, run, blob):
    for src, ds in CAT:
        d = root / f"source={src}" / f"dataset={ds}" / "ingest_date=2026-10-27" / f"run={run}"
        d.mkdir(parents=True)
        obj = f"_objects/sha256={blob}"
        (d / "_manifest.json").write_text(json.dumps({
            "run_id": run, "source": src, "dataset": ds, "entries": [{"object": obj}]}))
    (root / "_objects").mkdir(exist_ok=True)
    (root / "_objects" / f"sha256={blob}").write_bytes(blob.encode() * 10)


def listing(root, only=None):
    out = {}
    for f in root.rglob("*"):
        if f.is_file():
            k = f.relative_to(root).as_posix()
            if only is None or only(k):
                out[k] = f.stat().st_size
    return out


def test_synced_runs_pruned_unsynced_kept(tmp_path):
    for i, run in enumerate(["A1", "B2", "C3"]):
        land(tmp_path, run, f"blob{i}")
    synced = listing(tmp_path, lambda k: "A1" not in k and "blob0" not in k)
    synced.update(listing(tmp_path, lambda k: "A1" in k and False))
    # A1 and its blob are NOT in S3: oldest run is unsynced, so it must stay
    prune_raw.prune(tmp_path, synced, keep=1)
    assert (tmp_path / "_objects" / "sha256=blob0").exists()
    assert any("run=A1" in str(p) for p in tmp_path.rglob("_manifest.json"))
    # B2 is synced and outside the newest 1: pruned
    assert not (tmp_path / "_objects" / "sha256=blob1").exists()
    assert not any("run=B2" in str(p) for p in tmp_path.rglob("_manifest.json"))
    # C3 is retained
    assert (tmp_path / "_objects" / "sha256=blob2").exists()


def test_size_mismatch_is_not_synced(tmp_path):
    land(tmp_path, "A1", "blob0")
    land(tmp_path, "B2", "blob1")
    synced = {k: v + 1 for k, v in listing(tmp_path).items()}
    assert prune_raw.prune(tmp_path, synced, keep=1) == 0
    assert (tmp_path / "_objects" / "sha256=blob0").exists()
