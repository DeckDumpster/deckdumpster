#!/usr/bin/env bash
#
# Proxmox HTTP API wrapper — sourced by scripts in this directory.
#
# Provides pvapi(), which makes a single authenticated request and writes
# the response body to PVAPI_BODY and the HTTP status code to PVAPI_STATUS.
# Both are global variables; callers read them directly after each call.
#
# A connection error (curl exit ≠ 0) returns that exit code and leaves both
# globals empty. Callers must distinguish a curl failure from a 4xx response:
# curl failing means the API was not reached at all, which is not the same as
# "VM not found" (404). Never treat a connection failure as a 404.
#
# Both globals are reset at the start of every call so a stale value from a
# prior call is never read as the current one.
#
# Required environment variables (caller's responsibility):
#   PVE_HOST             — Proxmox hostname or IP
#   PVE_NODE             — Proxmox node name (e.g. pve)
#   PVE_API_TOKEN_ID     — API token id, e.g. gh-runner@pve!teardown
#   PVE_API_TOKEN_SECRET — API token secret UUID
#
# Uses --insecure because the Proxmox API on a loopback address ships with a
# self-signed certificate; the token carries the credential, not TLS chain.

PVAPI_STATUS=""
PVAPI_BODY=""

pvapi() {
    local method="$1" path="$2" body="${3:-}"
    PVAPI_STATUS=""
    PVAPI_BODY=""
    local _tmpfile _status _rc=0
    _tmpfile=$(mktemp)
    local -a _args=(
        -s -o "$_tmpfile" -w '%{http_code}'
        --insecure
        -X "$method"
        -H "Authorization: PVEAPIToken=${PVE_API_TOKEN_ID}=${PVE_API_TOKEN_SECRET}"
    )
    [ -n "$body" ] && _args+=(-H 'Content-Type: application/json' -d "$body")
    _status=$(curl "${_args[@]}" "https://${PVE_HOST}:8006/api2/json${path}") || _rc=$?
    PVAPI_STATUS="$_status"
    PVAPI_BODY=$(cat "$_tmpfile")
    rm -f "$_tmpfile"
    return "$_rc"
}
