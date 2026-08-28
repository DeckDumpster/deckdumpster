"""Quadlet rendering: the plaintext publish and the cert mount are both opt-in.

The load-bearing assertion is UNSET MEANS UNCHANGED — with no --http-port and no
--tls-certs the generated unit must be byte-identical to the pre-feature render.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "deploy" / "render-quadlet.sh"
TEMPLATE = REPO_ROOT / "deploy" / "mtgc.container"
SETUP = REPO_ROOT / "deploy" / "setup.sh"


PLACEHOLDERS = ("{{HTTP_PUBLISH}}", "{{TLS_MOUNT}}", "{{MEMORY_LIMIT}}")


def render(instance, port_mapping, http_port, tls_certs="", memory_max=""):
    result = subprocess.run(
        [
            "bash",
            str(RENDER),
            instance,
            port_mapping,
            http_port,
            tls_certs,
            memory_max,
            str(TEMPLATE),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def legacy_render(instance, port_mapping):
    """The exact sed pipeline setup.sh used before the placeholders existed."""
    template = TEMPLATE.read_text()
    template = "".join(
        line
        for line in template.splitlines(keepends=True)
        if line.strip() not in PLACEHOLDERS
    )
    return template.replace("{{PORT}}:8081", port_mapping).replace(
        "{{INSTANCE}}", instance
    )


@pytest.mark.parametrize("port_mapping", [":8081", "8081:8081", "8083:8081"])
def test_unset_http_port_renders_byte_identical_unit(port_mapping):
    assert render("myinst", port_mapping, "") == legacy_render("myinst", port_mapping)


def test_unset_http_port_publishes_nothing_extra():
    unit = render("myinst", ":8081", "")
    publishes = [ln for ln in unit.splitlines() if ln.startswith("PublishPort=")]
    assert publishes == ["PublishPort=:8081"]
    assert "{{HTTP_PUBLISH}}" not in unit


def test_http_port_renders_loopback_publish():
    unit = render("myinst", ":8081", "8083")
    publishes = [ln for ln in unit.splitlines() if ln.startswith("PublishPort=")]
    assert publishes == ["PublishPort=:8081", "PublishPort=127.0.0.1:8083:8080"]


def test_http_publish_is_never_wildcard_or_bare():
    """A 0.0.0.0 or bare publish would expose plaintext to the LAN."""
    unit = render("myinst", "8081:8081", "8083")
    for line in unit.splitlines():
        if line.startswith("PublishPort=") and line.endswith(":8080"):
            assert line == "PublishPort=127.0.0.1:8083:8080"
    assert "0.0.0.0" not in unit


def test_bind_address_is_not_operator_supplied():
    """The render hardcodes 127.0.0.1 — it takes a port, never an address."""
    unit = render("myinst", ":8081", "192")  # a port that looks like an address octet
    assert "PublishPort=127.0.0.1:192:8080" in unit


def test_non_numeric_http_port_is_rejected():
    result = subprocess.run(
        ["bash", str(RENDER), "myinst", ":8081", "0.0.0.0:8083", "", "", str(TEMPLATE)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "must be numeric" in result.stderr
    assert "0.0.0.0" not in result.stdout


def test_setup_accepts_http_port_flag():
    assert "--http-port" in SETUP.read_text()


# --- Host certificate directory mount ---------------------------------------


@pytest.mark.parametrize("port_mapping", [":8081", "8081:8081"])
def test_unset_tls_certs_renders_byte_identical_unit(port_mapping):
    """UNSET MEANS UNCHANGED: no --tls-certs, no trace of the placeholder."""
    unit = render("myinst", port_mapping, "", "")
    assert unit == legacy_render("myinst", port_mapping)
    assert "{{TLS_MOUNT}}" not in unit
    assert "/certs" not in unit


def test_unset_tls_certs_mounts_only_the_data_volume():
    volumes = [
        ln for ln in render("myinst", ":8081", "", "").splitlines()
        if ln.startswith("Volume=")
    ]
    assert volumes == ["Volume=mtgc-myinst-data:/data:Z"]


def test_tls_certs_renders_read_only_mount_at_certs():
    unit = render("myinst", ":8081", "", "%h/.config/mtgc/certs")
    volumes = [ln for ln in unit.splitlines() if ln.startswith("Volume=")]
    assert volumes == [
        "Volume=mtgc-myinst-data:/data:Z",
        "Volume=%h/.config/mtgc/certs:/certs:ro,Z",
    ]


def test_tls_mount_accepts_an_absolute_host_path():
    unit = render("myinst", ":8081", "", "/etc/mtgc-certs")
    assert "Volume=/etc/mtgc-certs:/certs:ro,Z" in unit


def test_tls_mount_is_always_read_only():
    """The app reads certificates; it must never be able to write them back."""
    for directory in ("%h/.config/mtgc/certs", "/srv/certs", "/srv/certs/"):
        unit = render("myinst", ":8081", "", directory)
        cert_mounts = [
            ln for ln in unit.splitlines()
            if ln.startswith("Volume=") and ":/certs:" in ln
        ]
        assert cert_mounts == [f"Volume={directory}:/certs:ro,Z"]


def test_tls_mount_combines_with_the_http_publish():
    unit = render("myinst", "8081:8081", "8083", "/srv/certs")
    assert "PublishPort=127.0.0.1:8083:8080" in unit
    assert "Volume=/srv/certs:/certs:ro,Z" in unit


@pytest.mark.parametrize(
    "bad",
    [
        "relative/certs",  # not absolute
        "~/certs",  # unexpanded tilde is not a path systemd understands
        "/srv/certs:rw",  # would smuggle a mount flag
        "/srv/certs:/data",  # would remount the data path
        "/srv/certs,rw",  # would append an option
        "/srv/certs\nExec=oops",  # would inject a unit directive
    ],
)
def test_unsafe_tls_certs_dir_is_rejected(bad):
    result = subprocess.run(
        ["bash", str(RENDER), "myinst", ":8081", "", bad, "", str(TEMPLATE)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "tls certs dir" in result.stderr
    assert "/certs" not in result.stdout


def test_setup_accepts_tls_certs_flag():
    assert "--tls-certs" in SETUP.read_text()


# --- Memory ceiling (de-4u8g) ------------------------------------------------
#
# The CI runner was OOM-killed with ~10 polecats in flight and does not
# auto-restart, so CI was dead ~24 h. Each instance is its own
# mtgc-<instance>.service with its own cgroup, so a limit on the runner unit
# does not reach the containers doing the allocating.


@pytest.mark.parametrize("port_mapping", [":8081", "8081:8081"])
def test_unset_memory_max_renders_byte_identical_unit(port_mapping):
    """UNSET MEANS UNCHANGED: this is how prod's unit is rendered."""
    unit = render("myinst", port_mapping, "", "", "")
    assert unit == legacy_render("myinst", port_mapping)
    assert "{{MEMORY_LIMIT}}" not in unit
    assert "Memory" not in unit


def test_memory_max_renders_a_single_directive():
    """MemoryMax and nothing else — no MemoryHigh to keep in sync, and a
    container that has died is easier to read than one that has been throttled."""
    unit = render("myinst", ":8081", "", "", "2G")
    memory = [ln for ln in unit.splitlines() if ln.startswith("Memory")]
    assert memory == ["MemoryMax=2G"]


def test_memory_max_lands_in_the_service_section():
    """A [Container] MemoryMax is not a directive Quadlet knows; the cgroup
    limit belongs to the generated service."""
    unit = render("myinst", ":8081", "", "", "2G")
    sections = {}
    current = None
    for line in unit.splitlines():
        if line.startswith("["):
            current = line
            sections[current] = []
        elif current and line:
            sections[current].append(line)
    assert "MemoryMax=2G" in sections["[Service]"]


@pytest.mark.parametrize("value", ["2048", "512K", "512M", "2G", "1T"])
def test_memory_max_accepts_systemd_sizes(value):
    assert f"MemoryMax={value}" in render("myinst", ":8081", "", "", value)


@pytest.mark.parametrize(
    "bad",
    [
        "2GB",  # systemd size suffixes are single letters
        "2 G",
        "infinity",  # a real systemd value, but not one this script hands out
        "50%",
        "2G\nExecStartPre=oops",  # would inject a unit directive
    ],
)
def test_unparseable_memory_max_is_rejected(bad):
    """A size systemd refuses is a unit that never loads — fail here, loudly,
    rather than shipping a container that cannot start."""
    result = subprocess.run(
        ["bash", str(RENDER), "myinst", ":8081", "", "", bad, str(TEMPLATE)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "memory max" in result.stderr
    assert "MemoryMax" not in result.stdout


# --- No renewal strategy is shipped (de-0ue) ---
#
# Obtaining and renewing a certificate is the operator's problem. The app only
# reads what it is pointed at. Shipping a sample renewal unit would bless one
# strategy (a tool, a cadence) when none has been chosen, so no unit exists and
# nothing in the deploy path may grow a dependency on one.

DEPLOY = REPO_ROOT / "deploy"
DEPLOY_README = DEPLOY / "README.md"


def test_no_cert_renewal_units_are_shipped():
    """No mtgc-cert-renew.* unit, and nothing in the deploy path references one."""
    assert not list(DEPLOY.glob("mtgc-cert-renew.*"))
    assert "cert-renew" not in SETUP.read_text()
    assert "cert-renew" not in TEMPLATE.read_text()
    assert "cert-renew" not in DEPLOY_README.read_text()


def test_readme_states_the_san_misconception():
    """Fixing the self-signed certificate's SAN does not stop browser warnings —
    trust is checked before naming. Re-deriving this cost real time once."""
    readme = DEPLOY_README.read_text()
    assert "## Trusted certificates" in readme
    assert "subjectAltName" in readme
    # Both recipes, and which one is recommended.
    assert "tailscale cert" in readme
    assert "DNS-01" in readme
    assert "MTGC_TLS_CERT" in readme and "MTGC_TLS_KEY" in readme
