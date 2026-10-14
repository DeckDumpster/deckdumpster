"""Raw landing zone: every byte fetched from upstream is kept (lakehouse 3, K1).

Every upstream fetch goes through this module, so the catalog can be rebuilt
from scratch, offline, from what was landed. Nothing here parses or alters a
payload; it is verbatim.

Layout under the landing root (the same keys the lake bucket will carry)::

    source=<s>/dataset=<d>/ingest_date=<YYYY-MM-DD>/run=<ULID>/_manifest.json
    source=<s>/dataset=<d>/ingest_date=<YYYY-MM-DD>/run=<ULID>/<name>   (small, kept forever)
    _objects/sha256=<hex>                                               (bulk, content-addressed)

Retention is per dataset (K1). A small payload (prices, API pages) is written
into the run's partition every time. A *bulk* payload (full-catalog snapshots,
~1 GB a night) is stored once under its SHA-256: a run whose content matches an
already-landed object writes no new object and records a manifest entry that
points at the existing one.

The manifest is rewritten atomically after every entry, so a killed run leaves
a manifest naming exactly what landed.
"""

import hashlib
import json
import os
import shutil
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from mtg_collector.utils import get_mtgc_home

USER_AGENT = "MTGCollectionTool/2.0"

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    n = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    return "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


def landing_root() -> Path:
    env = os.environ.get("MTGC_LAKE_RAW_DIR")
    return Path(env) if env else get_mtgc_home() / "lake" / "raw"


class Run:
    """One refresh's landing: a run id, a partition per (source, dataset), a manifest each."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else landing_root()
        self.run_id = new_ulid()
        self.ingest_date = datetime.now(timezone.utc).date().isoformat()
        self._entries: dict[tuple[str, str], list[dict]] = {}

    def _partition(self, source: str, dataset: str) -> Path:
        return (
            self.root
            / f"source={source}"
            / f"dataset={dataset}"
            / f"ingest_date={self.ingest_date}"
            / f"run={self.run_id}"
        )

    def _write_manifest(self, source: str, dataset: str) -> None:
        part = self._partition(source, dataset)
        part.mkdir(parents=True, exist_ok=True)
        doc = {
            "run_id": self.run_id,
            "source": source,
            "dataset": dataset,
            "ingest_date": self.ingest_date,
            "entries": self._entries[(source, dataset)],
        }
        tmp = part / "_manifest.json.tmp"
        tmp.write_text(json.dumps(doc, indent=2, sort_keys=True))
        os.replace(tmp, part / "_manifest.json")

    def _record(self, source, dataset, entry) -> dict:
        self._entries.setdefault((source, dataset), []).append(entry)
        self._write_manifest(source, dataset)
        return entry

    def land_bytes(self, *, source: str, dataset: str, url: str, data: bytes,
                   name: str | None = None, bulk: bool = False) -> dict:
        digest = hashlib.sha256(data).hexdigest()
        base = {
            "url": url,
            "sha256": digest,
            "size": len(data),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "bulk": bulk,
        }
        if bulk:
            obj = self.root / "_objects" / f"sha256={digest}"
            existed = obj.exists()
            if not existed:
                obj.parent.mkdir(parents=True, exist_ok=True)
                tmp = obj.with_name(obj.name + ".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, obj)
            return self._record(source, dataset, {
                **base, "object": str(obj.relative_to(self.root)), "deduplicated": existed,
            })
        part = self._partition(source, dataset)
        part.mkdir(parents=True, exist_ok=True)
        fname = name or f"{len(self._entries.get((source, dataset), [])):06d}-{digest[:12]}"
        (part / fname).write_bytes(data)
        return self._record(source, dataset, {
            **base, "object": str((part / fname).relative_to(self.root)), "deduplicated": False,
        })

    def land_file(self, *, source: str, dataset: str, url: str, path: Path) -> dict:
        """Land a downloaded bulk file without reading it into memory."""
        h = hashlib.sha256()
        size = 0
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
                size += len(chunk)
        digest = h.hexdigest()
        obj = self.root / "_objects" / f"sha256={digest}"
        existed = obj.exists()
        if not existed:
            obj.parent.mkdir(parents=True, exist_ok=True)
            tmp = obj.with_name(obj.name + ".tmp")
            shutil.copyfile(path, tmp)
            os.replace(tmp, obj)
        return self._record(source, dataset, {
            "url": url, "sha256": digest, "size": size, "bulk": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "object": str(obj.relative_to(self.root)), "deduplicated": existed,
        })

    def fetch(self, url: str, *, source: str, dataset: str, timeout: float | None = None,
              bulk: bool = False) -> bytes:
        """GET a URL, land the body verbatim, return it. HTTP errors propagate unlanded."""
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        self.land_bytes(source=source, dataset=dataset, url=url, data=data, bulk=bulk)
        return data

    def download(self, url: str, dest: Path, *, source: str, dataset: str) -> None:
        """Stream a bulk URL to ``dest`` and land it content-addressed."""
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)
        self.land_file(source=source, dataset=dataset, url=url, path=dest)


class ReplayMiss(Exception):
    """The derive asked for a URL the chosen raw partition never landed."""


class ReplayResponse:
    """The slice of ``requests.Response`` the bulk client reads, served from a landed object."""

    status_code = 200

    def __init__(self, url: str, path: Path):
        self.url = url
        self._path = path
        self.headers = {"Content-Length": str(path.stat().st_size)}

    @property
    def content(self) -> bytes:
        return self._path.read_bytes()

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int = 1024 * 1024):
        with open(self._path, "rb") as f:
            yield from iter(lambda: f.read(chunk_size), b"")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ReplaySession:
    """Stands in for ``requests.Session`` so the unchanged import code reads the lake."""

    def __init__(self, replay: "Replay"):
        self._replay = replay
        self.headers: dict = {}

    def request(self, method: str, url: str, params=None, **kwargs) -> ReplayResponse:
        import requests

        full = requests.Request(method, url, params=params).prepare().url
        return ReplayResponse(full, self._replay.path_for(full))

    def get(self, url: str, **kwargs) -> ReplayResponse:
        return self.request("GET", url, **kwargs)


class Replay:
    """One landed run read back instead of the network (lakehouse 4).

    Selection is by run, never by URL: the newest run id under the root, or the one
    named, so a derive reads one coherent night. A URL that run did not land is a
    ``ReplayMiss`` -- there is no fall-through to the network and no older run.
    Landing is a no-op here: a derive writes no raw byte.
    """

    def __init__(self, root: Path | None = None, run_id: str | None = None):
        self.root = Path(root) if root else landing_root()
        manifests = sorted(self.root.glob("source=*/dataset=*/ingest_date=*/run=*/_manifest.json"))
        docs = [json.loads(m.read_text()) for m in manifests]
        runs = {d["run_id"] for d in docs}
        if not runs:
            raise ReplayMiss(f"no landed run under {self.root}")
        if run_id is not None and run_id not in runs:
            raise ReplayMiss(f"run {run_id} is not under {self.root}")
        self.run_id = run_id or max(runs)
        self._index: dict[str, dict] = {}
        for doc in docs:
            if doc["run_id"] != self.run_id:
                continue
            for e in doc["entries"]:
                self._index[e["url"]] = e

    def path_for(self, url: str) -> Path:
        entry = self._index.get(url)
        if entry is None:
            raise ReplayMiss(f"run {self.run_id} landed no {url}")
        return self.root / entry["object"]

    def fetch(self, url: str, **_) -> bytes:
        return self.path_for(url).read_bytes()

    def download(self, url: str, dest: Path, **_) -> None:
        shutil.copyfile(self.path_for(url), dest)

    def land_bytes(self, **_) -> dict:
        return {}

    def land_file(self, **_) -> dict:
        return {}

    def session(self) -> ReplaySession:
        return ReplaySession(self)


_run: "Run | Replay | None" = None


def current_run() -> "Run | Replay":
    """The process's run: one ULID for everything a refresh fetches."""
    global _run
    if _run is None:
        _run = Run()
    return _run


def reset_run() -> None:
    global _run
    _run = None


def use_replay(replay: Replay) -> None:
    """Route every fetch of this process through ``replay``."""
    global _run
    _run = replay
