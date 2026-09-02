"""The nightly backup must be seen surviving a tight disk, not just a roomy one.

`deploy/backup.sh` lost 42 of the 175 nights from 2026-03-05 — 24% — and every
one of them for want of free space on the single 98 GB root volume prod shares
with its own data volume, the retained tarballs and Podman's store (de-o4e). A
skipped night is permanent: `aws s3 sync` mirrors a directory, so a tarball that
was never written can never be backfilled. de-4e8 is about not losing the night,
so most of what is below puts the run on a disk that is too small and asserts on
what it reclaims, what it refuses to touch, and whether it then completes.

`podman`, `aws` and `df` are stubbed with PATH shims; `tar` is wrapped so the
staging directory can be photographed at the moment the archive is written,
which is where the peak lives. Everything else — sqlite, tar itself, find, du —
is real, and so is the resulting tarball: the last test restores it. That keeps
the suite in the unit tier with no container, no bucket and no credentials, and
no way for a test to reach the real prod volume.
"""

import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKUP = REPO_ROOT / "deploy" / "backup.sh"

MB = 1024 * 1024

# Answers `df --output=avail -B1 <dir>` as a real filesystem would: whatever the
# box has free, less whatever this instance's backup directory is holding right
# now. That is what makes the reclaim loop observable — deleting a tarball, or
# clearing a dead run's staging, moves the number the next iteration reads.
DF_STUB = """#!/usr/bin/env bash
used="$(du -sb "$DF_ACCOUNT_DIR" 2>/dev/null | cut -f1)"
echo "Avail"
echo "$(( DF_FREE_BASE - ${used:-0} ))"
"""

PODMAN_STUB = """#!/usr/bin/env bash
if [ "$1" = "volume" ] && [ "$2" = "exists" ]; then exit 0; fi
if [ "$1" = "volume" ] && [ "$2" = "inspect" ]; then echo "$FAKE_VOLUME_MOUNT"; exit 0; fi
echo "podman-stub: unexpected call: $*" >&2
exit 1
"""

# `s3 ls` is answered from a table of "<name> <size>" lines, so a test can say
# "S3 does not have this one" or "S3 has it at a different size" precisely.
AWS_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$AWS_CALL_LOG"
if [ "$2" = "ls" ]; then
    name="${3##*/}"
    size="$(awk -v n="$name" '$1 == n { print $2 }' "$AWS_S3_TABLE")"
    [ -n "$size" ] || exit 1
    echo "2026-08-26 03:06:04 ${size} ${name}"
    exit 0
fi
exit "${AWS_SYNC_RC:-0}"
"""

# Photographs staging at the instant the archive is written — the peak — then
# runs the real tar with the arguments it was given.
TAR_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$TAR_CALL_LOG"
find "$STAGING_SPY" -mindepth 1 > "$STAGING_SPY_LOG" 2>/dev/null || true
exec "$REAL_TAR" "$@"
"""


def _make_db(path, rows, table="collection"):
    """A real SQLite database, big enough that its size is the dominant term."""
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, blob TEXT)")
    conn.executemany(
        f"INSERT INTO {table} (blob) VALUES (?)", [("x" * 512,) for _ in range(rows)]
    )
    conn.commit()
    conn.close()


class Rig:
    """A throwaway box: one instance volume, one backup directory, one disk."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()

        self.volume = tmp_path / "volume" / "_data"
        self.volume.mkdir(parents=True)
        _make_db(self.volume / "collection.sqlite", 4000)
        for name, payload in (("source_images", b"jpeg-a"), ("ingest_images", b"jpeg-b")):
            (self.volume / name).mkdir()
            (self.volume / name / "photo.jpg").write_bytes(payload * 4096)

        self.backups = tmp_path / "backups"
        self.instance_dir = self.backups / "prod"
        self.daily = self.instance_dir / "daily"
        self.staging = self.instance_dir / "staging"
        self.daily.mkdir(parents=True)

        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.real_tar = shutil.which("tar")
        for name, body in (
            ("df", DF_STUB),
            ("podman", PODMAN_STUB),
            ("aws", AWS_STUB),
            ("tar", TAR_SHIM),
        ):
            stub = self.bin / name
            stub.write_text(body)
            stub.chmod(0o755)

        self.s3_table = tmp_path / "s3.tsv"
        self.s3_table.write_text("")
        self.aws_log = tmp_path / "aws.log"
        self.aws_log.touch()
        self.tar_log = tmp_path / "tar.log"
        self.tar_log.touch()
        self.staging_spy = tmp_path / "staging-at-tar-time.log"
        self.staging_spy.write_text("")

        self.free_base = 4096 * MB
        self.bucket = "gantt-mtgc-backup"
        self.sync_rc = 0

    # --- arranging the night ---

    @property
    def db_bytes(self):
        return (self.volume / "collection.sqlite").stat().st_size

    @property
    def shared_bytes(self):
        shared = self.volume / "shared.sqlite"
        return shared.stat().st_size if shared.exists() else 0

    @property
    def needed_bytes(self):
        """The script's own budget: snapshots + 40% for the tarball + 200 MB."""
        snapshots = self.db_bytes + self.shared_bytes
        return snapshots + (snapshots * 2 // 5) + 200 * MB

    def split(self, rows=8000):
        """Make this a split instance: a reference catalogue beside the collection.

        `setup.sh --test` and every instance created before the shared-ref volume
        existed look like this — `mtg db split --shared-out /data/shared.sqlite`
        onto the instance's own data volume, which is where `restore.sh` puts one
        back.
        """
        _make_db(self.volume / "shared.sqlite", rows, table="printings")

    def plant_daily(self, name, size, in_s3=True, s3_size=None):
        """A retained local tarball, optionally with an S3 object behind it."""
        path = self.daily / name
        with path.open("wb") as fh:
            fh.write(b"\0" * size)
        if in_s3:
            with self.s3_table.open("a") as fh:
                fh.write(f"{name} {s3_size if s3_size is not None else size}\n")
        return path

    def leave_dead_staging(self, size):
        """What a run killed mid-snapshot leaves behind: its EXIT trap never fired."""
        self.staging.mkdir(parents=True, exist_ok=True)
        with (self.staging / "collection.sqlite").open("wb") as fh:
            fh.write(b"\0" * size)

    def free_space(self, avail):
        """Set the disk so `avail` bytes are free, counting what is on it right now.

        Order matters: anything planted afterwards eats into `avail`, which is
        how a dead run's staging is made to look like space this run cannot have.
        """
        used = sum(f.stat().st_size for f in self.instance_dir.rglob("*") if f.is_file())
        self.free_base = avail + used

    # --- running it ---

    def run(self):
        env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.home),
            "MTGC_BACKUP_DIR": str(self.backups),
            # An empty store root makes deploy/store-lib.sh a strict no-op, so
            # the podman shim above is the one that answers.
            "MTGC_STORE_ROOT": "",
            "FAKE_VOLUME_MOUNT": str(self.volume),
            "DF_FREE_BASE": str(self.free_base),
            "DF_ACCOUNT_DIR": str(self.instance_dir),
            "AWS_S3_TABLE": str(self.s3_table),
            "AWS_CALL_LOG": str(self.aws_log),
            "AWS_SYNC_RC": str(self.sync_rc),
            "TAR_CALL_LOG": str(self.tar_log),
            "REAL_TAR": self.real_tar,
            "STAGING_SPY": str(self.staging),
            "STAGING_SPY_LOG": str(self.staging_spy),
        }
        if self.bucket is not None:
            env["MTGC_BACKUP_S3_BUCKET"] = self.bucket
        return subprocess.run(
            ["bash", str(BACKUP), "prod"],
            capture_output=True,
            text=True,
            env=env,
        )

    # --- reading the aftermath ---

    @property
    def dailies(self):
        return sorted(p.name for p in self.daily.glob("mtgc-*.tar.gz"))

    @property
    def staging_at_tar_time(self):
        return [
            Path(line).name
            for line in self.staging_spy.read_text().splitlines()
            if line.strip()
        ]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_a_roomy_night_produces_a_restorable_tarball(rig, tmp_path):
    """The whole contract restore.sh depends on, end to end."""
    result = rig.run()
    assert result.returncode == 0, result.stdout + result.stderr

    tarball = next(iter(rig.daily.glob("mtgc-prod-*.tar.gz")))
    restored = tmp_path / "restored"
    restored.mkdir()
    with tarfile.open(tarball) as tf:
        names = tf.getnames()
        with tf.extractfile("collection.sqlite") as src:
            (restored / "collection.sqlite").write_bytes(src.read())
        with tf.extractfile("source_images/photo.jpg") as src:
            photo = src.read()
    assert "collection.sqlite" in names
    assert "source_images/photo.jpg" in names
    assert "ingest_images/photo.jpg" in names

    conn = sqlite3.connect(restored / "collection.sqlite")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM collection").fetchone()[0] == 4000
    conn.close()
    assert photo == (rig.volume / "source_images" / "photo.jpg").read_bytes()


def test_images_are_never_staged(rig):
    """~1 GB on prod that the run no longer has to have free.

    The budget only ever set 200 MB aside for the image trees, so copying them
    into staging could carry a run past a check it had already passed.
    """
    result = rig.run()
    assert result.returncode == 0, result.stdout + result.stderr

    assert rig.staging_at_tar_time == ["collection.sqlite"]
    tar_argv = rig.tar_log.read_text()
    assert f"-C {rig.volume} source_images" in tar_argv
    assert f"-C {rig.volume} ingest_images" in tar_argv


def test_an_instance_with_no_images_still_archives_the_directories(rig):
    """restore.sh copies both trees unconditionally, so both must be in there."""
    shutil.rmtree(rig.volume / "source_images")
    result = rig.run()
    assert result.returncode == 0, result.stdout + result.stderr

    tarball = next(iter(rig.daily.glob("mtgc-prod-*.tar.gz")))
    with tarfile.open(tarball) as tf:
        assert "source_images" in tf.getnames()
        assert "ingest_images/photo.jpg" in tf.getnames()


def test_a_dead_runs_staging_is_cleared_before_the_disk_is_measured(rig):
    """A killed run leaves up to a whole database behind; it is not a claim on the disk."""
    rig.free_space(rig.needed_bytes + 10 * MB)
    rig.leave_dead_staging(600 * MB)

    result = rig.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ERROR" not in result.stdout
    assert not rig.staging.exists()


def test_only_as_many_retained_backups_are_spent_as_the_night_needs(rig):
    """Reclaiming is a cost, so the run stops the moment it fits."""
    rig.plant_daily("mtgc-prod-20260825-030001.tar.gz", 40 * MB)
    rig.plant_daily("mtgc-prod-20260826-030001.tar.gz", 40 * MB)
    rig.free_space(rig.needed_bytes - 10 * MB)

    result = rig.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Reclaiming mtgc-prod-20260825-030001.tar.gz" in result.stdout
    assert "Reclaiming mtgc-prod-20260826-030001.tar.gz" not in result.stdout
    assert "mtgc-prod-20260826-030001.tar.gz" in rig.dailies


def test_every_retained_backup_is_spent_when_one_is_not_enough(rig):
    rig.plant_daily("mtgc-prod-20260825-030001.tar.gz", 40 * MB)
    rig.plant_daily("mtgc-prod-20260826-030001.tar.gz", 40 * MB)
    rig.free_space(rig.needed_bytes - 60 * MB)

    result = rig.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Reclaiming mtgc-prod-20260825-030001.tar.gz" in result.stdout
    assert "Reclaiming mtgc-prod-20260826-030001.tar.gz" in result.stdout


def test_a_roomy_night_spends_nothing(rig):
    """Retention is unchanged when the disk is not the problem."""
    rig.plant_daily("mtgc-prod-20260825-030001.tar.gz", 40 * MB)
    rig.plant_daily("mtgc-prod-20260826-030001.tar.gz", 40 * MB)
    rig.free_space(rig.needed_bytes + 500 * MB)

    result = rig.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Reclaiming" not in result.stdout
    assert "s3 ls" not in rig.aws_log.read_text()


def test_a_backup_s3_does_not_hold_is_never_deleted(rig):
    """The local copy is the only copy, and the night is worth less than it."""
    rig.plant_daily("mtgc-prod-20260825-030001.tar.gz", 40 * MB, in_s3=False)
    rig.free_space(rig.needed_bytes - 10 * MB)

    result = rig.run()

    assert result.returncode == 1
    assert "Keeping mtgc-prod-20260825-030001.tar.gz — S3 has no such object" in result.stdout
    assert rig.dailies == ["mtgc-prod-20260825-030001.tar.gz"]


def test_a_size_mismatch_is_not_a_copy(rig):
    """A half-uploaded object answers `s3 ls` too."""
    rig.plant_daily("mtgc-prod-20260825-030001.tar.gz", 40 * MB, s3_size=17)
    rig.free_space(rig.needed_bytes - 10 * MB)

    result = rig.run()

    assert result.returncode == 1
    assert "Keeping mtgc-prod-20260825-030001.tar.gz — S3 has 17" in result.stdout
    assert rig.dailies == ["mtgc-prod-20260825-030001.tar.gz"]


def test_without_a_bucket_nothing_local_is_spent(rig):
    """Local-only mode has no second copy to fall back on."""
    rig.bucket = None
    rig.plant_daily("mtgc-prod-20260825-030001.tar.gz", 40 * MB)
    rig.free_space(rig.needed_bytes - 10 * MB)

    result = rig.run()

    assert result.returncode == 1
    assert "Reclaiming" not in result.stdout
    assert rig.dailies == ["mtgc-prod-20260825-030001.tar.gz"]


def test_a_refusal_names_the_database_it_could_not_fit(rig):
    """The bar rises ~91 MB a day with the database; the message has to say so."""
    rig.free_space(10 * MB)

    result = rig.run()

    assert result.returncode == 1
    db_mb = rig.db_bytes // MB
    assert f"for a {db_mb} MB database" in result.stdout
    assert "were reclaimed first" in result.stdout


def test_the_shape_of_2026_08_11_now_completes(rig):
    """The second of the two nights de-o4e traced, at this rig's scale.

    That night the check wanted 14115 MB and the disk had 10479 — short by 26%
    of the requirement, with two retained tarballs of ~2.9 GB sitting on the
    same filesystem and both already in S3. Spending them clears it.
    """
    tarball_size = int(rig.db_bytes * 0.3) + 40 * MB
    rig.plant_daily("mtgc-prod-20260809-030001.tar.gz", tarball_size)
    rig.plant_daily("mtgc-prod-20260810-030001.tar.gz", tarball_size)
    rig.free_space(int(rig.needed_bytes * 0.74))

    result = rig.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert rig.daily.glob("mtgc-prod-*.tar.gz")
    assert "s3 sync" in rig.aws_log.read_text()


def test_a_disk_that_cannot_be_measured_is_a_failure(rig):
    """"We could not ask" is not "there is room" — the rule diskcheck.sh applies."""
    (rig.bin / "df").write_text("#!/usr/bin/env bash\nexit 1\n")
    (rig.bin / "df").chmod(0o755)
    rig.plant_daily("mtgc-prod-20260825-030001.tar.gz", 40 * MB)

    result = rig.run()

    assert result.returncode == 1
    assert "could not measure free space" in result.stdout
    assert rig.dailies == ["mtgc-prod-20260825-030001.tar.gz"]


# --- The shared catalogue of a split instance (de-hal) ---
#
# `restore.sh` has always had an "if present" branch for shared.sqlite, and it
# could never be true: nothing put the file in the tarball. A restore onto a
# fresh volume therefore landed an instance whose every shared table is a temp
# view over a file that is not there — no cards, no printings, no sets, and no
# price series, which is append-only and cannot be re-fetched for a day gone by.


def test_a_split_instances_catalogue_is_in_the_tarball(rig, tmp_path):
    """The whole point: restore.sh's `if present` can now be true."""
    rig.split()
    result = rig.run()
    assert result.returncode == 0, result.stdout + result.stderr

    tarball = next(iter(rig.daily.glob("mtgc-prod-*.tar.gz")))
    restored = tmp_path / "restored"
    restored.mkdir()
    with tarfile.open(tarball) as tf:
        assert "shared.sqlite" in tf.getnames()
        with tf.extractfile("shared.sqlite") as src:
            (restored / "shared.sqlite").write_bytes(src.read())

    conn = sqlite3.connect(restored / "shared.sqlite")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM printings").fetchone()[0] == 8000
    conn.close()


def test_a_monolithic_instance_archives_no_catalogue(rig):
    """shared.sqlite is what tells restore.sh the instance is split.

    The image trees contribute an empty directory when the instance has never
    had one, because restore.sh copies those unconditionally. An empty stand-in
    here would instead announce a split that did not happen.
    """
    result = rig.run()
    assert result.returncode == 0, result.stdout + result.stderr

    tarball = next(iter(rig.daily.glob("mtgc-prod-*.tar.gz")))
    with tarfile.open(tarball) as tf:
        assert "shared.sqlite" not in tf.getnames()


def test_the_catalogue_is_snapshotted_not_copied(rig):
    """It is a live WAL database, written by mtgc-prices and mtgc-catalog-refresh.

    A plain copy leaves the WAL behind and under sustained writes is missing
    frames — the rule tests/ui/conftest.py restores under. Being in staging at
    tar time is what says it went through sqlite3.backup(); the image trees, by
    contrast, are read straight from the volume mount and are never staged.
    """
    rig.split()
    result = rig.run()
    assert result.returncode == 0, result.stdout + result.stderr

    assert sorted(rig.staging_at_tar_time) == ["collection.sqlite", "shared.sqlite"]


def test_the_catalogue_counts_against_the_disk_budget(rig):
    """Both snapshots are on the disk at once, so both are part of the peak.

    A night sized for the collection alone would pass the check and then run out
    mid-snapshot — which is not how running out of disk presents (at 697 MB free
    a cargo link once reported `ld terminated with signal 7 [Bus error]`).
    """
    rig.split()
    collection_only = rig.db_bytes + (rig.db_bytes * 2 // 5) + 200 * MB
    rig.free_space(collection_only + 5 * MB)

    result = rig.run()

    assert result.returncode == 1
    shared_mb = rig.shared_bytes // MB
    assert f"plus a {shared_mb} MB shared catalogue" in result.stdout


def test_a_split_night_that_fits_still_completes(rig):
    """The budget rose; it did not become unmeetable."""
    rig.split()
    rig.free_space(rig.needed_bytes + 10 * MB)

    result = rig.run()

    assert result.returncode == 0, result.stdout + result.stderr
    tarball = next(iter(rig.daily.glob("mtgc-prod-*.tar.gz")))
    with tarfile.open(tarball) as tf:
        assert "shared.sqlite" in tf.getnames()
        assert "collection.sqlite" in tf.getnames()
