#!/usr/bin/env bash
#
# SSH forced-command dispatcher.
#
# Install at /usr/local/lib/gh-ephemeral-runner/forced-command.sh and name
# it in the hypervisor's authorized_keys so the workflow's SSH key is confined
# to the three runner scripts and nothing else.
#
# Parses $SSH_ORIGINAL_COMMAND into words without eval, validates the verb
# and every argument against positive patterns, then execs the matching
# script. Token delivery for provision.sh passes through stdin unchanged —
# the key never carries it on the command line, which would land it in sshd
# logs and the process table.
#
# Argument validation rules (reject, never sanitise):
#   provision.sh <label> <repo-url>   label: ^[A-Za-z0-9._-]+$
#                                     repo-url: ^https://github\.com/...
#   teardown.sh  <vmid>               vmid: ^[0-9]+$
#   reap.sh      [--max-age-hours N]  N: ^[0-9]+$
#                [--dry-run]
#
# Every accepted and refused invocation is logged with the verb and validated
# arguments only — never the token, never the raw command string (which may
# contain an injection attempt).
#
# set -e is intentional: an unexpected error must never silently fall through
# to an exec.
#
set -euo pipefail

SCRIPTS_DIR="${SCRIPTS_DIR:-/usr/local/lib/gh-ephemeral-runner}"
LOG_FILE="${LOG_FILE:-/var/log/gh-ephemeral-runner-cmd.log}"
CRED_FILE="${CRED_FILE:-/etc/gh-ephemeral-runner/token}"

# Source the credential file before dispatching so every script this invokes
# inherits TEMPLATE_VMID (and credentials) from the same place provision.sh
# reads them. Without this, TEMPLATE_VMID defaults to 101 in the dispatched
# scripts even when the real template has a different id.
if [ -f "$CRED_FILE" ]; then
    # shellcheck source=/dev/null
    . "$CRED_FILE"
    export TEMPLATE_VMID
fi

_log() {
    printf '%s forced-command: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
        >> "$LOG_FILE" 2>/dev/null || true
}

# On refusal: log the verb + reason, say nothing useful to the caller.
# A message that echoes the rejected string back is a probing oracle.
_refuse() {
    local reason="$1"
    _log "REFUSED verb=${VERB:-<empty>} reason=$reason client=${SSH_CONNECTION:-unknown}"
    exit 1
}

# --- Parse ---

if [ -z "${SSH_ORIGINAL_COMMAND:-}" ]; then
    VERB=""
    _refuse "empty command"
fi

# Split into an array without eval. Word-splitting on a here-string is safe
# because we validate every element before using it and never re-expand.
read -r -a WORDS <<< "$SSH_ORIGINAL_COMMAND"
VERB="${WORDS[0]:-}"
ARGS=("${WORDS[@]:1}")
ARGC="${#ARGS[@]}"

# --- Dispatch on the verb alone; never pattern-match the whole string ---

case "$VERB" in

    provision.sh)
        # provision.sh <label> <repo-url>
        # Registration token arrives on stdin and is forwarded unchanged.
        if [ "$ARGC" -ne 2 ]; then
            _refuse "wrong arity for provision.sh: got $ARGC args, want 2"
        fi
        LABEL="${ARGS[0]}"
        REPO_URL="${ARGS[1]}"
        if ! [[ "$LABEL" =~ ^[A-Za-z0-9._-]+$ ]]; then
            _refuse "invalid label"
        fi
        if ! [[ "$REPO_URL" =~ ^https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(/[A-Za-z0-9._/-]*)?$ ]]; then
            _refuse "invalid repo URL"
        fi
        _log "ACCEPTED provision.sh label=$LABEL repo=$REPO_URL client=${SSH_CONNECTION:-unknown}"
        exec "$SCRIPTS_DIR/provision.sh" "$LABEL" "$REPO_URL"
        ;;

    teardown.sh)
        # teardown.sh <vmid>
        if [ "$ARGC" -ne 1 ]; then
            _refuse "wrong arity for teardown.sh: got $ARGC args, want 1"
        fi
        VMID="${ARGS[0]}"
        if ! [[ "$VMID" =~ ^[0-9]+$ ]]; then
            _refuse "invalid VMID"
        fi
        _log "ACCEPTED teardown.sh vmid=$VMID client=${SSH_CONNECTION:-unknown}"
        exec "$SCRIPTS_DIR/teardown.sh" "$VMID"
        ;;

    reap.sh)
        # reap.sh [--max-age-hours N] [--dry-run]
        # Only these two flags are permitted; anything else is refused.
        REAP_ARGS=()
        i=0
        while [ "$i" -lt "$ARGC" ]; do
            case "${ARGS[$i]}" in
                --dry-run)
                    REAP_ARGS+=("--dry-run")
                    ;;
                --max-age-hours)
                    i=$(( i + 1 ))
                    if [ "$i" -ge "$ARGC" ]; then
                        _refuse "reap.sh --max-age-hours missing value"
                    fi
                    N="${ARGS[$i]}"
                    if ! [[ "$N" =~ ^[0-9]+$ ]]; then
                        _refuse "invalid --max-age-hours value"
                    fi
                    REAP_ARGS+=("--max-age-hours" "$N")
                    ;;
                *)
                    _refuse "unknown reap.sh flag: ${ARGS[$i]}"
                    ;;
            esac
            i=$(( i + 1 ))
        done
        _log "ACCEPTED reap.sh args=${REAP_ARGS[*]:-<none>} client=${SSH_CONNECTION:-unknown}"
        if (( ${#REAP_ARGS[@]} > 0 )); then
            exec "$SCRIPTS_DIR/reap.sh" "${REAP_ARGS[@]}"
        else
            exec "$SCRIPTS_DIR/reap.sh"
        fi
        ;;

    *)
        _refuse "unknown verb"
        ;;
esac
