"""The production container shape with two tenants, for the integration and UI tiers (sp-ntlyxy).

Two defects reached multi-tenant prod untested because every earlier check ran
somewhere other than where prod runs: the isolation gate drives the app
in-process, and the listener bug only exists behind a published port. So this
stands up the instance's own image the way the Quadlet does -- a container,
`-p 127.0.0.1::8080`, `MTGC_MULTITENANT=1`, Cloudflare Access verified against a
JWKS -- and every request goes through the published port.

The data is the demo dataset (collection, decks, binders, sealed, batches,
wishlist, orders) moved onto tenant `alice` by `mtg tenant legacy-migrate`, the
route prod takes. `bobby` is created empty. The pre-tenancy `collection.sqlite`
stays on the volume as `MTGC_DB`, as it does in prod: a handler that falls back to
the server's own file serves it to everybody, and that is the defect this exists
to catch.

The JWKS server runs in a sidecar container that joins the main container's
network namespace, so the verifier's URL is the container's own loopback. A
published-port container cannot reach the host's loopback, which is why
`handles.sh`'s host-network arm could never have noticed the bind bug.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from tests.container_store import podman_argv

HEADER = "Cf-Access-Jwt-Assertion"
JWKS_PORT = 18099
TOKEN_TTL_S = 6 * 3600
ALICE = "alice@example.org"
BOBBY = "bobby@example.org"
_JWKS_SCRIPT = Path(__file__).resolve().parent / "jwks_server.py"

_ACCESS_ENV = {
    "MTGC_ACCESS_TEAM_DOMAIN": "https://gate.cloudflareaccess.com",
    "MTGC_ACCESS_AUD": "gate-aud-tag",
    "MTGC_ACCESS_JWKS_URL": f"http://127.0.0.1:{JWKS_PORT}/certs",
}


class Tenant:
    """One tenant's view of the stack: JSON over the published port."""

    def __init__(self, base: str, email: str, token: str):
        self.base, self.email, self.token = base, email, token

    @property
    def headers(self) -> dict:
        return {HEADER: self.token}

    def raw(self, method: str, path: str, data: dict | None = None):
        body = None if data is None else json.dumps(data).encode()
        headers = dict(self.headers)
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def json(self, method: str, path: str, data: dict | None = None):
        status, body = self.raw(method, path, data)
        return status, json.loads(body)

    def get(self, path: str):
        return self.json("GET", path)

    def text(self, path: str) -> str:
        status, body = self.raw("GET", path)
        assert status == 200, f"{path} -> {status}"
        return body.decode("utf-8", "replace")


class TwoTenantStack:
    def __init__(self, instance: str):
        self.instance = instance
        self.image = f"localhost/mtgc:{instance}"
        self.podman = podman_argv(instance)
        tag = f"{int(time.time())}-{id(self) % 10000}"
        self.volume = f"mtgc-twot-{tag}"
        self.container = f"mtgc-twot-{tag}"
        self.sidecar = f"mtgc-twot-jwks-{tag}"
        self.work = Path(tempfile.mkdtemp(prefix="twot."))
        self.base = ""
        self.alice: Tenant
        self.bobby: Tenant

    # -- podman ---------------------------------------------------------------
    def _run(self, *args, check=True, timeout=600):
        result = subprocess.run(
            [*self.podman, *args], capture_output=True, text=True, timeout=timeout,
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"podman {' '.join(args[:6])} failed ({result.returncode}):\n"
                f"{result.stdout}\n{result.stderr}"
            )
        return result

    def _mtg(self, *args):
        return self._run(
            "run", "--rm", "-v", f"{self.volume}:/data:Z",
            "-e", "MTGC_HOME=/data", "-e", "MTGC_MULTITENANT=1",
            "--entrypoint", "mtg", self.image, *args,
        )

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> "TwoTenantStack":
        try:
            self._start()
        except BaseException:
            self.stop()
            raise
        return self

    def _start(self):
        if self._run("image", "exists", self.image, check=False).returncode != 0:
            raise RuntimeError(
                f"no image {self.image}: run deploy/setup.sh {self.instance} --test first"
            )
        self._run("volume", "create", self.volume)
        self._mtg("setup", "--demo", "--from-fixture", "/app/test-data.sqlite")
        self._mtg("db", "split", "--shared-out", "/data/shared.sqlite", "--prune")
        self._mtg("tenant", "legacy-migrate", "alice", "/data/collection.sqlite",
                  "--legacy-shared", "/data/shared.sqlite")
        self._mtg("tenant", "create", "bobby")
        self._mtg("tenant", "identity", "add", "alice", ALICE)
        self._mtg("tenant", "identity", "add", "bobby", BOBBY)

        env = []
        for k, v in {
            "MTGC_HOME": "/data", "MTGC_DB": "/data/collection.sqlite",
            "MTGC_MULTITENANT": "1", "MTGC_HTTP_PORT": "8080", **_ACCESS_ENV,
        }.items():
            env += ["-e", f"{k}={v}"]
        self._run("run", "-d", "--name", self.container,
                  "-p", "127.0.0.1::8080", "-v", f"{self.volume}:/data:Z", *env, self.image)

        shutil.copy(_JWKS_SCRIPT, self.work / "jwks_server.py")
        (self.work / "out").mkdir()
        self._run(
            "run", "-d", "--name", self.sidecar, "--network", f"container:{self.container}",
            "-v", f"{self.work}:/jwks:Z",
            "-e", f"JWKS_PORT={JWKS_PORT}", "-e", f"JWKS_TOKEN_TTL={TOKEN_TTL_S}",
            "--entrypoint", "python", self.image,
            "/jwks/jwks_server.py", "serve", "/jwks/out", ALICE, BOBBY,
        )

        port = self._published_port()
        self.base = f"http://127.0.0.1:{port}"
        self._wait("/health")
        ready = self.work / "out" / "ready"
        self._until(ready.exists, "the JWKS sidecar to write its tokens")
        tok = lambda email: (self.work / "out" / f"token.{email}").read_text()  # noqa: E731
        self.alice = Tenant(self.base, ALICE, tok(ALICE))
        self.bobby = Tenant(self.base, BOBBY, tok(BOBBY))

    def _published_port(self) -> str:
        out = self._run("port", self.container, "8080/tcp").stdout.strip()
        return out.splitlines()[0].rsplit(":", 1)[1]

    def _until(self, predicate, what: str, tries: int = 120):
        for _ in range(tries):
            if predicate():
                return
            time.sleep(1)
        logs = self._run("logs", "--tail", "60", self.container, check=False)
        raise RuntimeError(f"timed out waiting for {what}\n{logs.stdout}\n{logs.stderr}")

    def _wait(self, path: str):
        def up():
            try:
                return urllib.request.urlopen(self.base + path, timeout=3).status == 200
            except (urllib.error.URLError, OSError):
                return False
        self._until(up, f"{self.base}{path}")

    def stop(self):
        for name in (self.sidecar, self.container):
            self._run("rm", "-f", name, check=False)
        self._run("volume", "rm", "-f", self.volume, check=False)
        shutil.rmtree(self.work, ignore_errors=True)



def image_exists(instance: str) -> bool:
    return subprocess.run(
        [*podman_argv(instance), "image", "exists", f"localhost/mtgc:{instance}"],
        capture_output=True,
    ).returncode == 0


def start_stack(instance: str) -> TwoTenantStack:
    return TwoTenantStack(instance).start()


__all__ = ["ALICE", "BOBBY", "Tenant", "TwoTenantStack", "image_exists", "start_stack"]
