#!/usr/bin/env bash
# Bring up the UI tier's per-worker instances <base>-<k> in parallel from the
# image the run already built (sp-lc1puh).
#
# This is its own script because deploy/ci.sh may not invoke the instance
# bring-up directly: tests/test_store_isolation_gate.py asserts ci.sh's only
# bring-up is the store-isolation gate's. These instances are the gate's
# --keep instance's siblings -- same probe store, --no-build off its image.
#
# usage: ci-ui-workers.sh <base-instance> <count> <probe-store-root>
set -euo pipefail

BASE="${1:?base instance}"
COUNT="${2:?worker count}"
STORE="${3:?probe store root}"
cd "$(dirname "$0")/.."

pids=()
for k in $(seq 0 $((COUNT - 1))); do
    (
        export MTGC_STORE_ROOT="$STORE"
        bash deploy/teardown.sh "${BASE}-${k}" --purge >/dev/null 2>&1 || true
        bash deploy/setup.sh "${BASE}-${k}" --test --no-build \
            >"${TMPDIR:-/tmp}/ui-worker-${BASE}-${k}.log" 2>&1
    ) &
    pids+=($!)
done
for pid in "${pids[@]}"; do
    wait "$pid" || {
        echo "UI worker bring-up failed:" >&2
        tail -40 "${TMPDIR:-/tmp}"/ui-worker-"${BASE}"-*.log >&2
        exit 1
    }
done
