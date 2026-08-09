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


PLACEHOLDERS = ("{{HTTP_PUBLISH}}", "{{TLS_MOUNT}}")


def render(instance, port_mapping, http_port, tls_certs=""):
    result = subprocess.run(
        ["bash", str(RENDER), instance, port_mapping, http_port, tls_certs, str(TEMPLATE)],
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
        ["bash", str(RENDER), "myinst", ":8081", "0.0.0.0:8083", "", str(TEMPLATE)],
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
        ["bash", str(RENDER), "myinst", ":8081", "", bad, str(TEMPLATE)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "tls certs dir" in result.stderr
    assert "/certs" not in result.stdout


def test_setup_accepts_tls_certs_flag():
    assert "--tls-certs" in SETUP.read_text()
