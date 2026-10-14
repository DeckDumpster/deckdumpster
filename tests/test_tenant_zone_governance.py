"""deploy/setup-tenant-zone.sh and the policy documents (lakehouse bead 10).

Hermetic: the aws CLI is a stub whose answers are set per test, so the
classification of what the CLI said into exits 0/1/3/4 is seen red for every
case.  The container tier (tests/lake/tenant_zone.sh) is where a real
credential is really denied by MinIO.
"""

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from mtg_collector.lake import resolve

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "deploy" / "setup-tenant-zone.sh"
POLICIES = REPO / "deploy" / "policies" / "tenant-zone"

STUB = """#!/usr/bin/env bash
case "$*" in
*get-caller-identity*) echo "stub: no sts" >&2; exit 255 ;;
*get-bucket-lifecycle-configuration*)
    if [ -n "${FAKE_GET_ERR:-}" ]; then echo "$FAKE_GET_ERR" >&2; exit 254; fi
    printf '%s' "$FAKE_LIFECYCLE" ;;
*put-bucket-lifecycle-configuration*)
    if [ -n "${FAKE_PUT_ERR:-}" ]; then echo "$FAKE_PUT_ERR" >&2; exit 254; fi
    printf '%s' "$*" >"$FAKE_LOG" ;;
esac
"""

GOOD = json.loads((POLICIES / "lifecycle.json").read_text())


def rule(prefix, days=90, status="Enabled", shape="filter"):
    r = {"ID": "r", "Status": status, "Expiration": {"Days": days}}
    if shape == "filter":
        r["Filter"] = {"Prefix": prefix}
    elif shape == "and":
        r["Filter"] = {"And": {"Prefix": prefix}}
    else:
        r["Prefix"] = prefix
    return {"Rules": [r]}


@pytest.fixture
def run(tmp_path):
    aws = tmp_path / "aws"
    aws.write_text(STUB)
    aws.chmod(aws.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "conf").mkdir()

    def _run(*args, lifecycle=None, get_err="", put_err="", env_file=None, bucket=("--bucket", "lake-b")):
        env = {
            "PATH": os.environ["PATH"], "HOME": str(tmp_path),
            "MTGC_AWS": str(aws), "MTGC_CONFIG_DIR": str(tmp_path / "conf"),
            "FAKE_LIFECYCLE": json.dumps(lifecycle) if lifecycle is not None else "",
            "FAKE_GET_ERR": get_err, "FAKE_PUT_ERR": put_err, "FAKE_LOG": str(tmp_path / "put.log"),
        }
        if env_file is not None:
            (tmp_path / "conf" / "prod.env").write_text(env_file)
        return subprocess.run(["bash", str(SCRIPT), *args, *bucket], env=env, capture_output=True, text=True, timeout=60)

    _run.put_log = tmp_path / "put.log"
    return _run


# --- the four answers ----------------------------------------------------

def test_correct_rule_is_0(run):
    r = run("--check", lifecycle=GOOD)
    assert r.returncode == 0, r.stderr
    assert "90 days" in r.stdout


@pytest.mark.parametrize("doc", [
    rule(""),                                  # whole bucket: would expire the catalog
    rule("tenant/", days=365),                 # wrong window
    rule("raw/"),                              # reaches the catalog
    rule("lake/catalog/"),
    rule("", shape="legacy"),
    {"Rules": GOOD["Rules"] + rule("raw/")["Rules"]},   # right rule plus a bad second
], ids=["whole-bucket", "365-days", "raw", "lake", "legacy-empty", "good-plus-raw"])
def test_wrong_rule_is_1(run, doc):
    r = run("--check", lifecycle=doc)
    assert r.returncode == 1, r.stdout + r.stderr


@pytest.mark.parametrize("shape", ["filter", "and", "legacy"])
def test_every_prefix_spelling_is_read(run, shape):
    assert run("--check", lifecycle=rule("tenant/", shape=shape)).returncode == 0
    assert run("--check", lifecycle=rule("raw/", shape=shape)).returncode == 1


def test_absent_is_3(run):
    r = run("--check", get_err="An error occurred (NoSuchLifecycleConfiguration) when calling")
    assert r.returncode == 3
    assert "ABSENT" in r.stderr


def test_a_document_that_does_not_cover_the_zone_is_3(run):
    assert run("--check", lifecycle={"Rules": []}).returncode == 3
    assert run("--check", lifecycle=rule("tenant/", status="Disabled")).returncode == 3
    assert run("--check", lifecycle=rule("other/")).returncode == 3


def test_bad_rule_outranks_absence(run):
    doc = {"Rules": rule("raw/")["Rules"]}
    assert run("--check", lifecycle=doc).returncode == 1


@pytest.mark.parametrize("err", [
    "An error occurred (AccessDenied) when calling the GetBucketLifecycleConfiguration",
    "Forbidden",
    "Could not connect to the endpoint URL",
    "something nobody anticipated",
])
def test_cannot_read_is_4_never_3(run, err):
    r = run("--check", get_err=err)
    assert r.returncode == 4, r.stderr
    assert "ABSENT" not in r.stderr.replace("NOT \"there is no retention rule\"", "")
    assert "CANNOT VERIFY" in r.stderr


def test_access_denied_names_the_permission(run):
    r = run("--check", get_err="AccessDenied")
    assert "s3:GetLifecycleConfiguration" in r.stderr


def test_apply_puts_the_rule_then_verifies(run):
    r = run("--apply", lifecycle=GOOD)
    assert r.returncode == 0, r.stderr
    assert "put-bucket-lifecycle-configuration" in run.put_log.read_text()
    assert '"Days": 90' in run.put_log.read_text()


def test_apply_denied_is_1_and_says_who_may(run):
    r = run("--apply", lifecycle=GOOD, put_err="AccessDenied")
    assert r.returncode == 1
    assert "s3:PutLifecycleConfiguration" in r.stderr


def test_apply_whose_readback_cannot_read_is_4(run):
    r = run("--apply", get_err="AccessDenied")
    assert r.returncode == 4


def test_apply_whose_readback_disagrees_is_not_success(run):
    assert run("--apply", lifecycle=rule("tenant/", days=30)).returncode == 1


# --- refusals ------------------------------------------------------------

def test_usage_is_2(run):
    assert run().returncode == 2
    assert run("--check", "--bogus").returncode == 2


def test_no_bucket_is_refused_naming_the_env_file(run):
    r = run("--check", lifecycle=GOOD, bucket=())
    assert r.returncode == 1
    assert "MTGC_LAKE_S3_BUCKET" in r.stderr


def test_bucket_from_the_instance_env_file(run):
    r = run("--check", lifecycle=GOOD, bucket=(), env_file="MTGC_LAKE_S3_BUCKET=from-env\n")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("var", ["MTGC_BACKUP_S3_BUCKET", "MTGC_LITESTREAM_S3_BUCKET"])
def test_the_backup_buckets_are_refused(run, var):
    r = run("--apply", lifecycle=GOOD, bucket=("--bucket", "same"), env_file=f"{var}=same\n")
    assert r.returncode == 1
    assert "BACKUP" in r.stderr
    assert not run.put_log.exists()


# --- rendering and the three homes of the prefixes -----------------------

def test_render_substitutes_every_placeholder(run, tmp_path):
    out = tmp_path / "out"
    r = run("--render", "--out", str(out), "--backup-bucket", "bk", "--litestream-bucket", "ls")
    assert r.returncode == 0, r.stderr
    for name in ("catalog-credentials", "tenant-credentials"):
        text = (out / f"{name}.json").read_text()
        assert "{{" not in text
        json.loads(text)
        assert "lake-b" in text and "bk" in text and "ls" in text


def _statements(name):
    return json.loads((POLICIES / f"{name}.json").read_text())["Statement"]


def _flat(x):
    return [x] if isinstance(x, str) else list(x)


def test_policies_are_mirror_images():
    cat, ten = _statements("catalog-credentials"), _statements("tenant-credentials")
    for stmts, own, other in ((cat, resolve.CATALOG_PREFIXES, resolve.TENANT_PREFIX),
                              (ten, (resolve.TENANT_PREFIX,), resolve.CATALOG_PREFIXES)):
        allow = [s for s in stmts if s["Effect"] == "Allow"]
        deny = [s for s in stmts if s["Effect"] == "Deny"]
        allowed = {r for s in allow for r in _flat(s["Resource"])}
        for p in own:
            assert f"arn:aws:s3:::{{{{BUCKET}}}}/{p}*" in allowed
        for p in _flat(other):
            assert not any(a.endswith(f"/{p}*") for a in allowed)
            assert any(f"arn:aws:s3:::{{{{BUCKET}}}}/{p}*" in _flat(s["Resource"]) and s["Action"] == "s3:*"
                       for s in deny), f"no explicit Deny on {p}"
        # nobody may rewrite the governance
        assert any("s3:PutLifecycleConfiguration" in _flat(s["Action"]) for s in deny)
        # nobody may touch the backup buckets
        assert any("arn:aws:s3:::{{BACKUP_BUCKET}}/*" in _flat(s["Resource"]) for s in deny)
        # listing is prefix scoped, never bucket-wide
        for s in allow:
            if "s3:ListBucket" in _flat(s["Action"]):
                assert "s3:prefix" in s["Condition"]["StringLike"]


def test_the_raw_zone_is_append_only():
    actions = {a for s in _statements("catalog-credentials") if s["Effect"] == "Allow" for a in _flat(s["Action"])}
    assert not {a for a in actions if "Delete" in a}
    ten = {a for s in _statements("tenant-credentials") if s["Effect"] == "Allow" for a in _flat(s["Action"])}
    assert {"s3:DeleteObject", "s3:DeleteObjectVersion"} <= ten


def test_prefixes_and_retention_have_not_drifted_across_their_homes():
    script = SCRIPT.read_text()
    assert re.search(r'^TENANT_PREFIX="%s"$' % re.escape(resolve.TENANT_PREFIX), script, re.M)
    assert re.search(r'^CATALOG_PREFIXES="%s"$' % " ".join(resolve.CATALOG_PREFIXES), script, re.M)
    assert re.search(r"^RETENTION_DAYS=%d$" % resolve.RETENTION_DAYS, script, re.M)
    (r,) = GOOD["Rules"]
    assert r["Filter"]["Prefix"] == resolve.TENANT_PREFIX
    assert r["Expiration"]["Days"] == resolve.RETENTION_DAYS
    sop = (REPO / "deploy" / "LAKE-SOP.md").read_text()
    assert f'"Prefix":"{resolve.TENANT_PREFIX}"' in sop.replace(" ", "")
    assert f'"Days":{resolve.RETENTION_DAYS}' in sop.replace(" ", "")


def test_lifecycle_json_passes_its_own_check(run):
    assert run("--check", lifecycle=GOOD).returncode == 0


def test_the_minio_gate_is_wired_into_ci():
    assert "bash tests/lake/tenant_zone.sh" in (REPO / "deploy" / "ci.sh").read_text()
