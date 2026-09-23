#!/usr/bin/env bash
# Compute DECKDUMP_CI_TIERS from a newline-delimited list of changed files on
# stdin. Prints the selected tier set to stdout.
#
# Rules:
#   all files match a known-cheap pattern → lint,unit
#   any unrecognised file, or no files    → lint,unit,integration,ui
#
# The second rule is deliberate. Narrowing on an unfamiliar path is how a
# regression ships undetected: a new feature lands in an unrecognised location,
# only lint+unit runs, and the integration gap is never caught.
#
# Known-cheap patterns (no container needed):
#   .github/workflows/**
#   tests/test_ci_entrypoint.py

set -euo pipefail

ALL="lint,unit,integration,ui"
CHEAP="lint,unit"

any=false
cheap=true

while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    any=true
    case "$f" in
        .github/workflows/* | tests/test_ci_entrypoint.py) ;;
        *) cheap=false; break ;;
    esac
done

if [[ "$any" == true && "$cheap" == true ]]; then
    echo "$CHEAP"
else
    echo "$ALL"
fi
