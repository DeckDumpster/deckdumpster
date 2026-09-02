"""A restore that reports OK over the wrong catalogue is the failure mode here.

`deploy/restore.sh` is the disaster-recovery path, and until de-hal its
shared.sqlite branch was unreachable — `backup.sh` never archived the file, so
`if [ -f "$STAGING_DIR/shared.sqlite" ]` could not be true. Every backup of a
split instance taken before that fix is a tarball with no catalogue in it, and
restoring one onto a split volume leaves the new collection beside whatever
catalogue was already there. Under split-DB every shared table is a temp view
over that file, so nothing on the collection side can see the mismatch and the
run prints "Restore complete!".

`podman`, `systemctl` and `sleep` are PATH shims; the "volume" is a directory
and every `podman cp` / `podman exec` is rewritten onto it, so the copies, the
guard's existence check and the final integrity check are all really executed.
No container, no image, no reachable prod volume.
"""

import sqlite3
import subprocess
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RESTORE = REPO_ROOT / "deploy" / "restore.sh"

# Maps a container path onto the directory standing in for the data volume, so
# `podman exec` runs the real command and `podman cp` performs the real copy.
PODMAN_STUB = """#!/usr/bin/env bash
resolve() {
    case "$1" in
        *":/data"*) printf '%s' "${FAKE_VOLUME}${1#*:/data}" ;;
        /data*)     printf '%s' "${FAKE_VOLUME}${1#/data}" ;;
        *)          printf '%s' "$1" ;;
    esac
}
printf '%s\\n' "$*" >> "$PODMAN_CALL_LOG"
case "$1" in
    volume)
        [ "$2" = "create" ] && mkdir -p "$FAKE_VOLUME"
        exit 0
        ;;
    run|rm) exit 0 ;;
    cp)
        cp -a "$(resolve "$2")" "$(resolve "$3")"
        exit $?
        ;;
    exec)
        shift 2
        args=()
        for a in "$@"; do args+=("${a//\\/data/$FAKE_VOLUME}"); done
        exec "${args[@]}"
        ;;
esac
echo "podman-stub: unexpected call: $*" >&2
exit 1
"""

NOOP_STUB = """#!/usr/bin/env bash
exit 0
"""


def _make_db(path, table, rows):
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, blob TEXT)")
    conn.executemany(
        f"INSERT INTO {table} (blob) VALUES (?)", [("x" * 64,) for _ in range(rows)]
    )
    conn.commit()
    conn.close()


class Rig:
    """One data volume, one tarball, and the stubs that stand between them."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.volume = tmp_path / "volume" / "_data"
        self.volume.mkdir(parents=True)

        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name, body in (
            ("podman", PODMAN_STUB),
            ("systemctl", NOOP_STUB),
            ("sleep", NOOP_STUB),
        ):
            stub = self.bin / name
            stub.write_text(body)
            stub.chmod(0o755)
        self.podman_log = tmp_path / "podman.log"
        self.podman_log.touch()

    # --- arranging ---

    def volume_holds(self, *, collection=100, shared=None):
        """What is on the volume before the restore runs."""
        _make_db(self.volume / "collection.sqlite", "collection", collection)
        if shared is not None:
            _make_db(self.volume / "shared.sqlite", "printings", shared)

    def tarball(self, *, collection=4000, shared=None):
        """A backup archive, with or without the catalogue of a split instance."""
        staging = self.tmp / "archive"
        staging.mkdir(exist_ok=True)
        _make_db(staging / "collection.sqlite", "collection", collection)
        members = ["collection.sqlite"]
        if shared is not None:
            _make_db(staging / "shared.sqlite", "printings", shared)
            members.append("shared.sqlite")
        for images in ("source_images", "ingest_images"):
            (staging / images).mkdir(exist_ok=True)
            (staging / images / "photo.jpg").write_bytes(b"jpeg" * 64)
            members.append(images)

        path = self.tmp / "backup.tar.gz"
        subprocess.run(
            ["tar", "czf", str(path), "-C", str(staging), *members], check=True
        )
        return path

    # --- running it ---

    def run(self, backup):
        return subprocess.run(
            ["bash", str(RESTORE), "--yes", str(backup), "prod"],
            capture_output=True,
            text=True,
            env={
                "PATH": f"{self.bin}:/usr/bin:/bin",
                "HOME": str(self.tmp / "home"),
                # An empty store root makes deploy/store-lib.sh a strict no-op.
                "MTGC_STORE_ROOT": "",
                "FAKE_VOLUME": str(self.volume),
                "PODMAN_CALL_LOG": str(self.podman_log),
            },
        )

    # --- reading the aftermath ---

    def rows(self, filename, table):
        conn = sqlite3.connect(self.volume / filename)
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            conn.close()


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_a_split_backup_restores_both_databases(rig):
    """The contract de-hal makes reachable: the catalogue comes back too.

    Without it a restore onto a fresh volume lands an instance whose every shared
    table is a temp view over a file that is not there — no cards, no printings,
    no sets, and a price series that is append-only and cannot be re-fetched.
    """
    backup = rig.tarball(collection=4000, shared=2500)

    result = rig.run(backup)

    assert result.returncode == 0, result.stdout + result.stderr
    assert rig.rows("collection.sqlite", "collection") == 4000
    assert rig.rows("shared.sqlite", "printings") == 2500
    assert "4000 collection entries, 2500 shared printings" in result.stdout


def test_a_backup_with_no_catalogue_is_refused_on_a_split_volume(rig):
    """A pre-de-hal tarball is exactly this shape, and it must not land quietly.

    The restored collection would be served beside the catalogue already on the
    volume, which nothing on the collection side can detect.
    """
    rig.volume_holds(collection=100, shared=7)
    backup = rig.tarball(collection=4000)

    result = rig.run(backup)

    assert result.returncode == 1
    assert "mtgc-prod-data is split (it has shared.sqlite) but this backup has none" in (
        result.stdout
    )
    # Refused means untouched — not half-restored.
    assert rig.rows("collection.sqlite", "collection") == 100
    assert rig.rows("shared.sqlite", "printings") == 7


def test_a_monolithic_restore_is_unaffected(rig):
    """prod is not split, and its nightly tarball still restores as it always did."""
    backup = rig.tarball(collection=4000)

    result = rig.run(backup)

    assert result.returncode == 0, result.stdout + result.stderr
    assert rig.rows("collection.sqlite", "collection") == 4000
    assert not (rig.volume / "shared.sqlite").exists()
    assert "OK — 4000 collection entries" in result.stdout


def test_a_split_backup_replaces_a_stale_catalogue(rig):
    """Restoring onto a volume that is already split overwrites what is there."""
    rig.volume_holds(collection=100, shared=7)
    backup = rig.tarball(collection=4000, shared=2500)

    result = rig.run(backup)

    assert result.returncode == 0, result.stdout + result.stderr
    assert rig.rows("shared.sqlite", "printings") == 2500


def test_the_images_still_come_back(rig):
    """Both trees are restored unconditionally; the catalogue is the only optional one."""
    backup = rig.tarball(collection=10, shared=10)

    result = rig.run(backup)

    assert result.returncode == 0, result.stdout + result.stderr
    for images in ("source_images", "ingest_images"):
        assert (rig.volume / images / "photo.jpg").read_bytes() == b"jpeg" * 64


def test_a_tarball_without_a_collection_is_not_a_backup(rig):
    """The pre-existing gate, kept honest by the new one landing beside it."""
    empty = rig.tmp / "not-a-backup.tar.gz"
    with tarfile.open(empty, "w:gz"):
        pass

    result = rig.run(empty)

    assert result.returncode == 1
    assert "does not contain collection.sqlite" in result.stdout
