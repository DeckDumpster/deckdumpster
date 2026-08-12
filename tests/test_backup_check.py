"""The backup freshness check must be seen going RED, not just green.

`deploy/backup-check.sh` is the dead-man's switch for the nightly backup of
mtgc-prod-data. A check that has only ever been observed passing is not known to
work — that is the whole defect it exists to remove — so most of what is below
drives it into each failure it claims to catch and asserts on the exit status,
the message, and the requests that left the script.

`aws` and `curl` are the script's only external calls, so both are stubbed with
PATH shims that record their argv. That keeps the suite in the unit tier: no
network, no bucket, no credentials, and no way for a test to touch the real
backup target.
"""

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK = REPO_ROOT / "deploy" / "backup-check.sh"
ALERT = REPO_ROOT / "deploy" / "alert.sh"

# Records argv, then replays a canned listing and exit code. AWS_STUB_RC is how
# a broken-credentials / unreachable-S3 run is expressed.
AWS_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$AWS_CALL_LOG"
cat "$AWS_STUB_OUT"
exit "${AWS_STUB_RC:-0}"
"""

CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$CURL_CALL_LOG"
exit 0
"""

PING_URL = "https://hc.example/deadbeef"
PUSHOVER_URL = "https://pushover.example/messages.json"


def s3_line(age_hours, size, key):
    ts = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return f"{ts.strftime('%Y-%m-%dT%H:%M:%S')}+00:00\t{size}\t{key}"


# A healthy bucket: last night's backup and the one before it, both ~3 GB.
HEALTHY = "\n".join(
    [
        s3_line(30, 3_183_156_942, "mtgc-prod/daily/mtgc-prod-20260810-030001.tar.gz"),
        s3_line(6, 3_216_229_803, "mtgc-prod/daily/mtgc-prod-20260812-030001.tar.gz"),
    ]
)


@pytest.fixture
def check(tmp_path):
    """Drive the real script against stubbed aws/curl and a throwaway config."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("aws", AWS_STUB), ("curl", CURL_STUB)):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)

    conf = tmp_path / "config"
    conf.mkdir()
    (conf / "alerts.env").write_text(
        f"PUSHOVER_TOKEN=tok\nPUSHOVER_USER=usr\nPUSHOVER_API_URL={PUSHOVER_URL}\n"
    )

    aws_log = tmp_path / "aws.log"
    curl_log = tmp_path / "curl.log"
    aws_out = tmp_path / "aws.out"
    aws_log.touch()
    curl_log.touch()

    class Check:
        def __init__(self):
            self.conf = conf

        def configure(self, instance="prod", **settings):
            """Write the instance env file the script reads."""
            defaults = {
                "MTGC_BACKUP_S3_BUCKET": "gantt-mtgc-backup",
                "MTGC_BACKUP_PING_URL": PING_URL,
            }
            defaults.update(settings)
            lines = [f"{k}={v}" for k, v in defaults.items() if v is not None]
            (conf / f"{instance}.env").write_text("\n".join(lines) + "\n")

        def run(self, listing=HEALTHY, rc=0, instance="prod"):
            aws_out.write_text(listing + ("\n" if listing else ""))
            if not (conf / "prod.env").exists():
                self.configure()
            env = dict(os.environ)
            env.update(
                PATH=f"{bin_dir}:{env['PATH']}",
                MTGC_CONFIG_DIR=str(conf),
                AWS_CALL_LOG=str(aws_log),
                CURL_CALL_LOG=str(curl_log),
                AWS_STUB_OUT=str(aws_out),
                AWS_STUB_RC=str(rc),
            )
            return subprocess.run(
                ["bash", str(CHECK), instance],
                capture_output=True,
                text=True,
                env=env,
            )

        @property
        def aws_calls(self):
            return aws_log.read_text().splitlines()

        @property
        def curl_calls(self):
            return curl_log.read_text().splitlines()

        def pinged(self, suffix=""):
            return any(PING_URL + suffix in c for c in self.curl_calls)

        @property
        def alerted(self):
            return any(PUSHOVER_URL in c for c in self.curl_calls)

    return Check()


# --- The green path ---------------------------------------------------------


def test_fresh_backup_passes_and_pings_the_monitor(check):
    result = check.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "backup-check: OK" in result.stdout
    assert check.pinged()
    assert not check.pinged("/fail")
    assert not check.alerted


def test_the_ping_reports_the_object_it_actually_verified(check):
    """The log has to name the object, or a green run says nothing checkable."""
    result = check.run()

    assert "mtgc-prod-20260812-030001.tar.gz" in result.stdout
    assert "3067 MiB" in result.stdout


# --- Every way it must go red ----------------------------------------------


def test_stale_backup_fails_and_trips_the_dead_man(check):
    """The failure this bead exists for: the upload silently stopped."""
    result = check.run(listing=s3_line(70, 3_216_229_803, "mtgc-prod/daily/old.tar.gz"))

    assert result.returncode == 1
    assert "STALE" in result.stderr
    assert "70h old" in result.stderr
    assert check.pinged("/fail")
    assert check.alerted


def test_empty_prefix_fails(check):
    """A bucket with nothing in it is the loudest possible failure, and the one
    a job-ran check would call success."""
    result = check.run(listing="")

    assert result.returncode == 1
    assert "NO objects" in result.stderr
    assert check.pinged("/fail")


def test_unreadable_bucket_fails_rather_than_passing_quietly(check):
    """Broken credentials — the Jun 2026 pokedumpster failure. 'We could not
    ask' must never land on the same side of the line as 'the answer is fine'."""
    result = check.run(listing="An error occurred (AccessDenied)", rc=255)

    assert result.returncode == 1
    assert "could not list" in result.stderr
    assert check.pinged("/fail")
    assert check.alerted


def test_zero_byte_backup_fails_the_size_floor(check):
    result = check.run(
        listing="\n".join(
            [
                s3_line(30, 3_183_156_942, "mtgc-prod/daily/yesterday.tar.gz"),
                s3_line(6, 0, "mtgc-prod/daily/today.tar.gz"),
            ]
        )
    )

    assert result.returncode == 1
    assert "0 bytes" in result.stderr
    assert check.pinged("/fail")


def test_truncated_backup_fails_against_the_previous_one(check):
    """Fresh, non-trivially sized, and missing two thirds of the collection —
    invisible to an age check and to any fixed floor low enough to be safe."""
    result = check.run(
        listing="\n".join(
            [
                s3_line(30, 3_183_156_942, "mtgc-prod/daily/yesterday.tar.gz"),
                s3_line(6, 1_000_000_000, "mtgc-prod/daily/today.tar.gz"),
            ]
        )
    )

    assert result.returncode == 1
    assert "content is missing" in result.stderr
    assert check.pinged("/fail")


def test_ordinary_growth_is_not_a_shrink(check):
    """The shrink check must not fire on the normal night-to-night delta, or it
    gets muted and stops being a check at all."""
    result = check.run()

    assert result.returncode == 0


def test_a_single_backup_passes_but_says_it_had_nothing_to_compare(check):
    result = check.run(listing=s3_line(6, 3_216_229_803, "mtgc-prod/daily/only.tar.gz"))

    assert result.returncode == 0
    assert "no previous backup to compare against" in result.stdout


# --- No configuration may turn the check into a pass ------------------------


def test_missing_bucket_fails_instead_of_skipping(check):
    """An instance with no off-site target has no backup to be fresh. Printing
    'skipping' and exiting 0 is indistinguishable, in a green unit, from a
    verified backup — the exact regression pokedumpster booked as pd-1717."""
    check.configure(MTGC_BACKUP_S3_BUCKET=None)
    result = check.run()

    assert result.returncode == 1
    assert "MTGC_BACKUP_S3_BUCKET is unset" in result.stderr
    assert check.aws_calls == []


def test_an_unarmed_monitor_still_verifies_freshness(check):
    """The ping URL gates the PING, never the verification."""
    check.configure(MTGC_BACKUP_PING_URL=None)
    result = check.run(listing=s3_line(70, 3_216_229_803, "mtgc-prod/daily/old.tar.gz"))

    assert result.returncode == 1
    assert "STALE" in result.stderr
    assert check.alerted
    assert not check.pinged("/fail")


def test_an_unarmed_monitor_says_so_on_the_green_path(check):
    check.configure(MTGC_BACKUP_PING_URL=None)
    result = check.run()

    assert result.returncode == 0
    assert "NOT armed" in result.stdout
    assert not check.pinged()


def test_a_dropped_alert_does_not_hide_the_stale_backup(check):
    """Pushover unconfigured: alert.sh fails, and the verdict is unaffected."""
    (check.conf / "alerts.env").write_text(f"PUSHOVER_API_URL={PUSHOVER_URL}\n")
    result = check.run(listing=s3_line(70, 3_216_229_803, "mtgc-prod/daily/old.tar.gz"))

    assert result.returncode == 1
    assert "reached nobody" in result.stderr
    assert check.pinged("/fail")


# --- It must not be able to damage what it watches --------------------------


def test_the_only_aws_call_is_a_read(check):
    check.run()

    assert len(check.aws_calls) == 1
    call = check.aws_calls[0]
    assert call.startswith("s3api list-objects-v2 ")
    assert "--bucket gantt-mtgc-backup" in call
    assert "--prefix mtgc-prod/" in call


def test_the_script_names_no_mutating_s3_operation(check):
    """Belt and braces on the above: the shipped source contains no write."""
    source = CHECK.read_text()
    for verb in ("put-object", "delete-object", "s3 cp", "s3 mv", "s3 rm", "s3 sync"):
        assert verb not in source


def test_the_prefix_is_scoped_to_the_instance(check):
    """A default prefix that reached the whole bucket would let one instance's
    fresh backup vouch for another's."""
    check.configure(instance="staging")
    result = check.run(instance="staging")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--prefix mtgc-staging/" in check.aws_calls[0]


def test_a_missing_instance_config_is_not_a_pass(check):
    """No env file at all — nothing configured, nothing to verify, not green."""
    result = check.run(instance="staging")

    assert result.returncode == 1
    assert "instance 'staging'" in result.stderr


# --- alert.sh ---------------------------------------------------------------


def test_alert_fails_when_it_cannot_reach_anyone(tmp_path):
    """Asked to alert and unable to alert is a failure, not a no-op."""
    result = subprocess.run(
        ["bash", str(ALERT), "title", "message"],
        capture_output=True,
        text=True,
        env={**os.environ, "PUSHOVER_TOKEN": "", "PUSHOVER_USER": ""},
    )

    assert result.returncode == 1
    assert "reached nobody" in result.stderr


def test_alert_treats_the_scaffolded_placeholder_as_unset(tmp_path):
    result = subprocess.run(
        ["bash", str(ALERT), "title", "message"],
        capture_output=True,
        text=True,
        env={**os.environ, "PUSHOVER_TOKEN": "CHANGE_ME", "PUSHOVER_USER": "CHANGE_ME"},
    )

    assert result.returncode == 1
    assert "reached nobody" in result.stderr


# --- The units ---------------------------------------------------------------


def test_units_are_installed_and_rendered(tmp_path):
    """setup.sh must actually install the check, or it ships inert."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "podman").write_text(
        "#!/usr/bin/env bash\ncase \"$1\" in volume) exit 1 ;; esac\nexit 0\n"
    )
    for name in ("systemctl", "loginctl"):
        (bin_dir / name).write_text("#!/usr/bin/env bash\nexit 0\n")
    for name in ("podman", "systemctl", "loginctl"):
        (bin_dir / name).chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        PATH=f"{bin_dir}:{env['PATH']}",
        XDG_RUNTIME_DIR=str(tmp_path / "run"),
    )
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "deploy" / "setup.sh"), "inst", "8099"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    units = home / ".config/systemd/user"
    service = (units / "mtgc-backup-check-inst.service").read_text()
    timer = (units / "mtgc-backup-check-inst.timer").read_text()
    alert = (units / "mtgc-alert-inst@.service").read_text()

    # No placeholder survives into an installed unit — an unrendered {{REPO_DIR}}
    # is a unit that fails only when the timer first fires, weeks later.
    for unit in (service, timer, alert):
        assert "{{" not in unit

    assert f"{REPO_ROOT}/deploy/backup-check.sh inst" in service
    assert "OnFailure=mtgc-alert-inst@%n.service" in service
    assert "WantedBy=timers.target" in timer
    assert f"{REPO_ROOT}/deploy/alert.sh" in alert
