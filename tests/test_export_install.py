"""scripts/export-install.sh archives a fixture install; the manifest must match it."""

import hashlib
import json
import sqlite3
import subprocess
import tarfile
from pathlib import Path

import pytest

from tests.subprocess_run import DEFAULT_TIMEOUT

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export-install.sh"

IMAGES = {
    "ingest_images/a.jpg": b"aaa",
    "ingest_images/sub/b.jpg": b"bbbb" * 100,
    "source_images/c.jpg": b"c",
}


@pytest.fixture
def install(tmp_path):
    home = tmp_path / "mtgc"
    home.mkdir()
    for rel, data in IMAGES.items():
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (home / "secrets.env").write_text("ANTHROPIC_API_KEY=x")
    (home / "cache").mkdir()
    (home / "cache" / "big.json").write_text("{}")
    conn = sqlite3.connect(home / "collection.sqlite")
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT);
        INSERT INTO schema_version VALUES (7, 'now');
        CREATE TABLE collection (id INTEGER PRIMARY KEY, source_image TEXT);
        INSERT INTO collection (source_image) VALUES ('/x/a.jpg'), ('/x/b.jpg');
        CREATE TABLE empty_t (id INTEGER);
        """
    )
    conn.commit()
    conn.close()
    return home


def run(*args):
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True,
        timeout=DEFAULT_TIMEOUT,
    )


def test_archive_matches_fixture(install, tmp_path):
    out = tmp_path / "out"
    r = run("--home", str(install), "--out", str(out))
    assert r.returncode == 0, r.stderr
    [archive] = list(out.glob("deckdumpster-export-*-*.tar.gz"))
    assert str(archive) in r.stdout
    assert not [p for p in out.iterdir() if p != archive]

    with tarfile.open(archive) as tf:
        names = {m.name for m in tf.getmembers() if m.isfile()}
        manifest = json.load(tf.extractfile("manifest.json"))
        db_bytes = tf.extractfile("collection.sqlite").read()
        blobs = {n: tf.extractfile(n).read() for n in names if n.startswith("images/")}

    assert names == {"manifest.json", "collection.sqlite"} | {f"images/{r}" for r in IMAGES}
    assert manifest["format"] == 1
    assert manifest["mtgc_home"] == str(install)
    assert manifest["schema_version"] == 7
    assert manifest["row_counts"] == {"collection": 2, "empty_t": 0, "schema_version": 1}
    assert {f["path"]: (f["size"], f["sha256"]) for f in manifest["files"]} == {
        f"images/{rel}": (len(d), hashlib.sha256(d).hexdigest()) for rel, d in IMAGES.items()
    }
    for n, data in blobs.items():
        assert data == IMAGES[n[len("images/"):]]

    snap = tmp_path / "snap.sqlite"
    snap.write_bytes(db_bytes)
    assert sqlite3.connect(snap).execute("SELECT COUNT(*) FROM collection").fetchone() == (2,)


def test_missing_database_fails(tmp_path):
    (tmp_path / "h").mkdir()
    r = run("--home", str(tmp_path / "h"), "--out", str(tmp_path))
    assert r.returncode != 0
    assert "database missing" in r.stderr


def test_unreadable_image_fails(install, tmp_path):
    (install / "ingest_images" / "dangling.jpg").symlink_to(tmp_path / "nowhere")
    r = run("--home", str(install), "--out", str(tmp_path / "out"))
    assert r.returncode != 0
    assert "dangling.jpg" in r.stderr
    assert not list((tmp_path / "out").glob("*.tar.gz"))
