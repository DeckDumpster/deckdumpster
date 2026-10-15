#!/usr/bin/env bash
#
# Install the pinned official Litestream release onto the host (sp-5sq7wk).
#
#   litestream-install.sh            install if missing or a different version
#
# Replication was configured, timers installed, and the binary never put on the
# host: litestream-run.sh calls `litestream replicate` from PATH, so an enabled
# unit would have failed on every start. Production tenant data had no backup
# from the 2026-10-14 cutover until it was found by hand. deploy.sh runs this,
# so the dependency is installed by the deploy that needs it.
#
# The tarball is checked against the sha256 pinned here before anything is
# unpacked; a mismatch is a hard error. Upgrading means changing VERSION and
# both digests together, from the release's checksums.txt.
set -euo pipefail

VERSION="0.5.17"
SHA256_X86_64="cfb371176d164437ae869f8351cfde49bd1804ae71c61923f75c9cba9c9c006d"
SHA256_ARM64="f8ca4a050095c1efbda2c4365172e61bf9d955ea0d9ac42f448b52e51819baa5"

BASE_URL="${MTGC_LITESTREAM_BASE_URL:-https://github.com/benbjohnson/litestream/releases/download/v${VERSION}}"
BIN_DIR="${MTGC_LITESTREAM_BIN_DIR:-$HOME/.local/bin}"

case "$(uname -m)" in
    x86_64)          ARCH=x86_64; SHA256="$SHA256_X86_64" ;;
    aarch64|arm64)   ARCH=arm64;  SHA256="$SHA256_ARM64" ;;
    *) echo "ERROR: no pinned litestream release for $(uname -m)" >&2; exit 1 ;;
esac

if [ -x "$BIN_DIR/litestream" ] \
        && "$BIN_DIR/litestream" version 2>/dev/null | grep -qx "v\?${VERSION}"; then
    echo "==> litestream ${VERSION} already installed at $BIN_DIR/litestream"
    exit 0
fi

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
TARBALL="litestream-${VERSION}-linux-${ARCH}.tar.gz"

echo "==> Fetching litestream ${VERSION} (${ARCH})"
curl -fsSL --max-time 300 -o "$SCRATCH/$TARBALL" "${BASE_URL}/${TARBALL}"
echo "${SHA256}  $SCRATCH/$TARBALL" | sha256sum -c --status - \
    || { echo "ERROR: $TARBALL does not match the pinned sha256 ${SHA256}" >&2; exit 1; }

tar xzf "$SCRATCH/$TARBALL" -C "$SCRATCH" litestream
mkdir -p "$BIN_DIR"
install -m 0755 "$SCRATCH/litestream" "$BIN_DIR/litestream.new"
mv -f "$BIN_DIR/litestream.new" "$BIN_DIR/litestream"
echo "==> Installed $BIN_DIR/litestream"
