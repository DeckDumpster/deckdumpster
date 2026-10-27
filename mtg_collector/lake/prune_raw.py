"""Bound the local raw landing zone once the bucket holds a verified copy (sp-ol9a3q).

Stdlib only: lake-sync.sh runs it on the host, outside the image.

A file is removed only if it is outside the retained set AND the bucket listing
names it at the same size. The retained set is the newest ``keep`` runs plus the
newest run that landed every catalogue input (what ``data derive`` reads), with
every ``_objects`` blob their manifests point at. Everything else local is a
second copy of what S3 already holds.

    prune_raw.py --root <raw> --listing <file of "<size> <key under raw/>"> [--keep N]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

CATALOG_DATASETS = {("scryfall", "default_cards"), ("mtgjson", "allprintings"), ("mtgjson", "meta")}


def _runs(root: Path):
    runs: dict[str, dict] = {}
    for m in root.glob("source=*/dataset=*/ingest_date=*/run=*/_manifest.json"):
        d = json.loads(m.read_text())
        r = runs.setdefault(d["run_id"], {"datasets": set(), "objects": set(), "dirs": []})
        if d["entries"]:
            r["datasets"].add((d["source"], d["dataset"]))
        r["objects"].update(e["object"] for e in d["entries"])
        r["dirs"].append(m.parent)
    return runs


def read_listing(path: Path) -> dict[str, int]:
    out = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            out[parts[1]] = int(parts[0])
    return out


def prune(root: Path, synced: dict[str, int], keep: int) -> int:
    runs = _runs(root)
    retained = set(sorted(runs)[-keep:])
    complete = [r for r, v in runs.items() if CATALOG_DATASETS <= v["datasets"]]
    if complete:
        retained.add(max(complete))
    kept_objects = set().union(*(runs[r]["objects"] for r in retained)) if retained else set()

    freed = 0

    def verified(f: Path) -> bool:
        return synced.get(f.relative_to(root).as_posix()) == f.stat().st_size

    for run_id, v in runs.items():
        if run_id in retained:
            continue
        for d in v["dirs"]:
            files = [f for f in d.rglob("*") if f.is_file()]
            if files and all(verified(f) for f in files):
                freed += sum(f.stat().st_size for f in files)
                shutil.rmtree(d)
    objects = root / "_objects"
    if objects.is_dir():
        for f in objects.iterdir():
            if f.is_file() and f.relative_to(root).as_posix() not in kept_objects and verified(f):
                freed += f.stat().st_size
                f.unlink()
    return freed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--listing", required=True)
    ap.add_argument("--keep", type=int, default=2)
    a = ap.parse_args(argv)
    freed = prune(Path(a.root), read_listing(Path(a.listing)), a.keep)
    print(f"lake-prune: freed {freed} bytes from {a.root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
