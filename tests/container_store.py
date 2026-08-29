"""Finding the test instance's container, in whichever Podman store it lives (de-1zq).

A bare ``podman`` only ever sees the DEFAULT store. ``MTGC_STORE_ROOT`` (de-3mo)
puts every non-prod instance in an alternate one via ``--root``/``--runroot``,
and ``deploy/setup.sh`` reads ``~/.config/mtgc/store.env`` for every instance
except prod (de-oqu) — so on an opted-in box the workflow CLAUDE.md documents

    bash deploy/setup.sh <inst> --test
    uv run pytest tests/integration/ --instance <inst>

lands the container in the alternate store and a bare ``podman port`` cannot see
it. That did not error: the conftests skipped, and ``124 skipped … exit 0`` reads
as a pass. Two individually correct features combined to silently disable the
integration and UI suites for anyone following the documented local instructions.
CI was never exposed — ``ci.yml`` activates the shim and exports it through
``GITHUB_PATH`` precisely so ``uv run pytest`` inherits it — which is why the
suites stayed green while the hand path measured nothing.

**The instance's Quadlet unit is the record.** systemd started the container with
that file's ``GlobalArgs=``, so it is a fact about where the container *is*, not
a preference about where one *should go*. That is why the unit beats
``MTGC_STORE_ROOT`` here while ``deploy/store-lib.sh`` lets an explicit variable
win: those scripts are choosing a store to act in, this is finding a container
that already exists. An **unstamped** unit names the default store just as
definitely — prod's unit never carries ``GlobalArgs=``, because ``setup.sh``
excludes prod by name — so ``--instance prod`` resolves correctly on a box whose
``store.env`` opts everything else in. Nothing here guesses, and nothing falls
through to "try the default store as well".

The runroot is never re-derived: it is read off the unit, or, when there is no
unit, out of ``store-lib.sh`` itself. Reproducing that hash in Python is exactly
how the two would drift apart.
"""

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STORE_LIB = _REPO_ROOT / "deploy" / "store-lib.sh"


def _shim_is_on_path() -> bool:
    """True when an ancestor already ran ``mtgc_store_activate``.

    The shim *is* a ``podman`` that appends the flags, so adding them again here
    would pass each one twice. CI takes this branch.
    """
    root = os.environ.get("MTGC_STORE_ROOT", "").rstrip("/")
    if not root:
        return False
    found = shutil.which("podman")
    return found is not None and Path(found).parent == Path(root) / "bin"


def _unit_global_args(instance: str):
    """The store flags recorded in the instance's Quadlet unit.

    Returns the flags, ``[]`` for an unstamped unit (the default store, decided),
    or None when there is no unit — an instance ``setup.sh`` did not install, so
    there is no record to read. ``$HOME`` is resolved per call so a test can
    point it somewhere else.
    """
    unit = (
        Path(os.path.expanduser("~"))
        / ".config/containers/systemd"
        / f"mtgc-{instance}.container"
    )
    if not unit.is_file():
        return None
    for line in unit.read_text().splitlines():
        if line.startswith("GlobalArgs="):
            return line.split("=", 1)[1].split()
    return []


@lru_cache(maxsize=None)
def _env_global_args(root: str):
    """The flags for ``MTGC_STORE_ROOT=<root>``, from store-lib.sh itself.

    Only reached with no unit to read: a container started by hand, or macOS,
    where ``mac-setup.sh`` runs ``podman run`` and knows nothing about stores.
    ``mtgc_store_activate`` is what derives the runroot, and asking it is what
    keeps this from becoming a second copy of that derivation.
    """
    if not root:
        return []
    result = subprocess.run(
        ["bash", "-c",
         f'. "{_STORE_LIB}" && mtgc_store_activate >/dev/null'
         ' && printf %s "$MTGC_STORE_GLOBAL_ARGS"'],
        capture_output=True, text=True, env={**os.environ, "MTGC_STORE_ROOT": root},
    )
    result.check_returncode()
    return result.stdout.split()


def podman_argv(instance: str) -> list:
    """``podman`` plus the flags that scope it to the store `instance` lives in."""
    if _shim_is_on_path():
        return ["podman"]
    flags = _unit_global_args(instance)
    if flags is None:
        flags = _env_global_args(os.environ.get("MTGC_STORE_ROOT", "").rstrip("/"))
    return ["podman", *flags]


def discover_container(instance: str):
    """The container name for `instance`, or None if it does not exist.

    Tries both patterns: ``systemd-mtgc-<name>`` (Linux Quadlet) and
    ``mtgc-<name>`` (macOS, ``podman run``).
    """
    for candidate in (f"systemd-mtgc-{instance}", f"mtgc-{instance}"):
        try:
            subprocess.run(
                [*podman_argv(instance), "container", "exists", candidate],
                capture_output=True, check=True,
            )
            return candidate
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None
