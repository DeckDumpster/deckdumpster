#!/usr/bin/env bash
# Archive a single-tenant deckdumpster install into one tarball:
#   deckdumpster-export-<host>-<UTC timestamp>.tar.gz
#     manifest.json                 format 1; counts and sha256s
#     collection.sqlite             consistent snapshot (sqlite3 .backup)
#     images/ingest_images/...      verbatim from $MTGC_HOME
#     images/source_images/...      verbatim from $MTGC_HOME
# Nothing else goes in: no code, caches, env files or keys.
# Needs only bash, sqlite3, tar and sha256sum or shasum.
#
# Usage: export-install.sh [--home DIR] [--out DIR]
set -euo pipefail

die() { echo "export-install: $*" >&2; exit 1; }

HOME_DIR="${MTGC_HOME:-$HOME/.mtgc}"   # same rule as mtg_collector.utils.get_mtgc_home
OUT_DIR="."
while [ $# -gt 0 ]; do
  case "$1" in
    --home) [ $# -ge 2 ] || die "--home needs a directory"; HOME_DIR="$2"; shift 2 ;;
    --out)  [ $# -ge 2 ] || die "--out needs a directory"; OUT_DIR="$2"; shift 2 ;;
    -h|--help) sed -n 2,11p "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

command -v sqlite3 >/dev/null || die "sqlite3 not found"
command -v tar >/dev/null || die "tar not found"
if command -v sha256sum >/dev/null; then sha() { sha256sum "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null; then sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
else die "neither sha256sum nor shasum found"; fi

[ -d "$HOME_DIR" ] || die "MTGC_HOME does not exist: $HOME_DIR"
HOME_DIR="$(cd "$HOME_DIR" && pwd)"
DB="$HOME_DIR/collection.sqlite"
[ -f "$DB" ] || die "database missing: $DB"
[ -r "$DB" ] || die "database unreadable: $DB"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

jstr() { local s="${1//\\/\\\\}"; s="${s//\"/\\\"}"; printf '"%s"' "$s"; }

# Every file the manifest would list, checked before any work is done.
FILES=()
for sub in ingest_images source_images; do
  d="$HOME_DIR/$sub"
  [ -d "$d" ] || continue
  bad="$(find "$d" ! -type f ! -type d -print -quit)"
  [ -z "$bad" ] || die "not a regular file or directory (symlinks and specials are not archived): $bad"
  while IFS= read -r -d '' f; do
    [ -r "$f" ] || die "image cannot be read: $f"
    FILES+=("${f#"$HOME_DIR"/}")
  done < <(find "$d" -type f -print0 | LC_ALL=C sort -z)
done

# Free space: snapshot copy + the archive (worst case incompressible).
db_bytes=$(wc -c < "$DB")
img_bytes=0
for rel in ${FILES[@]+"${FILES[@]}"}; do img_bytes=$(( img_bytes + $(wc -c < "$HOME_DIR/$rel") )); done
need=$(( 2 * db_bytes + img_bytes + 1048576 ))
avail=$(( $(df -Pk "$OUT_DIR" | awk 'NR==2{print $4}') * 1024 ))
[ "$avail" -ge "$need" ] || die "not enough free space in $OUT_DIR: need $need bytes, have $avail"

STAGE="$(mktemp -d "$OUT_DIR/.export-install.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

sqlite3 "$DB" ".backup '$STAGE/collection.sqlite'" || die "snapshot of $DB failed"

version="$(sqlite3 "$STAGE/collection.sqlite" 'SELECT COALESCE(MAX(version),0) FROM schema_version')"
commit=null
src="$(cd "$(dirname "$0")/.." && pwd)"
if c="$(git -C "$src" rev-parse HEAD 2>/dev/null)"; then commit="$(jstr "$c")"; fi

{
  printf '{\n  "format": 1,\n  "exported_at": %s,\n  "mtgc_home": %s,\n' \
    "$(jstr "$(date -u +%Y-%m-%dT%H:%M:%SZ)")" "$(jstr "$HOME_DIR")"
  printf '  "schema_version": %s,\n  "git_commit": %s,\n  "row_counts": {' "$version" "$commit"
  sep=""
  while IFS= read -r t; do
    n="$(sqlite3 "$STAGE/collection.sqlite" "SELECT COUNT(*) FROM \"$t\"")"
    printf '%s\n    %s: %s' "$sep" "$(jstr "$t")" "$n"; sep=","
  done < <(sqlite3 "$STAGE/collection.sqlite" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql NOT LIKE 'CREATE VIRTUAL%' ORDER BY name")
  printf '\n  },\n  "files": ['
  sep=""
  for rel in ${FILES[@]+"${FILES[@]}"}; do
    printf '%s\n    {"path": %s, "size": %s, "sha256": "%s"}' "$sep" \
      "$(jstr "images/$rel")" "$(wc -c < "$HOME_DIR/$rel" | tr -d ' ')" "$(sha "$HOME_DIR/$rel")"
    sep=","
  done
  printf '\n  ]\n}\n'
} > "$STAGE/manifest.json"

# images/ in the stage are symlinks; tar -h archives what they point at.
mkdir "$STAGE/images"
members=(manifest.json collection.sqlite)
for sub in ingest_images source_images; do
  mkdir -p "$STAGE/images/$sub"
  if [ -d "$HOME_DIR/$sub" ]; then
    rmdir "$STAGE/images/$sub"; ln -s "$HOME_DIR/$sub" "$STAGE/images/$sub"
  fi
  members+=("images/$sub")
done

ARCHIVE="$OUT_DIR/deckdumpster-export-$(hostname -s 2>/dev/null || hostname)-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar -czhf "$ARCHIVE" -C "$STAGE" "${members[@]}" || { rm -f "$ARCHIVE"; die "writing archive failed"; }

echo "archive: $ARCHIVE"
echo "size:    $(wc -c < "$ARCHIVE" | tr -d ' ') bytes"
echo "schema_version: $version, images: ${#FILES[@]}"
sed -n '/"row_counts"/,/^  }/p' "$STAGE/manifest.json" | grep -E '^    "' | tr -d ',' | sed 's/^    /  /'
