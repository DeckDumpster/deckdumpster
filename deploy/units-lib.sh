#!/usr/bin/env bash
#
# Installing this repo's timer units onto a host, for one instance.
#
# Sourced by setup.sh and by deploy.sh. Both of them, and that is the point:
# deploy.sh only delegates to setup.sh when the Quadlet file is MISSING, so for
# an instance that already exists — prod — a unit added to the repo after that
# instance was installed never reached the host at all. Three shipped timers
# (mtgc-catalog-check de-b5q, mtgc-catalog-refresh de-wdq, mtgc-diskcheck
# de-yef) were absent from prod for exactly that reason, months after they
# landed and with nothing anywhere saying so (de-46k).
#
# INSTALLING IS NOT ARMING, and re-installing does not disarm. This writes unit
# FILES and nothing else; enablement lives in `*.target.wants/` symlinks, which
# rewriting a unit file does not touch. So a re-run leaves an armed timer armed
# and a disarmed one disarmed, and a redeploy can be unconditional. Which
# timers an instance runs stays a decision someone makes once, per instance, by
# hand — see deploy/README.md.
#
# THE UNIT LIST IS THE DIRECTORY, not a list written down beside it. A second
# copy of "which timers exist" is the same bug one level up: a template added
# to deploy/ and forgotten in the list would install on no host at all, and the
# only symptom is a timer that never fires. Every `deploy/mtgc-*.timer` is
# installed, and a timer whose `.service` is missing is a hard error rather
# than a silently skipped pair.

# mtgc_units_list <repo_dir> — the unit prefixes this repo defines, one per
# line. Bash expands the glob in sorted order, so the output is stable without
# piping through sort — which also keeps the missing-.service case a real
# non-zero return instead of one swallowed by a pipeline's exit status.
# `mtgc-alert@.service` is deliberately not among them: it is a systemd
# instance template fired by OnFailure=, not a timer.
mtgc_units_list() {
    local repo_dir="$1"
    local timer prefix
    local -a prefixes=()
    for timer in "$repo_dir"/deploy/mtgc-*.timer; do
        [ -e "$timer" ] || continue
        prefix="$(basename "$timer" .timer)"
        if [ ! -f "$repo_dir/deploy/${prefix}.service" ]; then
            echo "ERROR: $prefix.timer has no matching $prefix.service" >&2
            return 1
        fi
        prefixes+=("$prefix")
    done
    if [ ${#prefixes[@]} -eq 0 ]; then
        echo "ERROR: no deploy/mtgc-*.timer templates found under $repo_dir" >&2
        return 1
    fi
    printf '%s\n' "${prefixes[@]}"
}

# mtgc_units_installed <instance> — the unit prefixes actually present on this
# host for one instance, one per line, or nothing at all.
#
# Removal reads the HOST, not the repo. The two lists are the same list right
# up until a template is deleted from deploy/, and then the repo has forgotten
# a unit the host still has — armed, firing, and belonging to an instance that
# no longer exists. Teardown has to be able to remove what it did not install.
mtgc_units_installed() {
    local instance="$1"
    local timer prefix base
    local -a prefixes=()
    for timer in "$HOME/.config/systemd/user"/mtgc-*-"${instance}".timer; do
        [ -e "$timer" ] || continue
        base="$(basename "$timer" .timer)"
        prefix="${base%-${instance}}"
        prefixes+=("$prefix")
    done
    [ ${#prefixes[@]} -gt 0 ] || return 0
    printf '%s\n' "${prefixes[@]}"
}

# mtgc_install_units <instance> <repo_dir> — render every timer unit plus the
# alert template for one instance into ~/.config/systemd/user, then reload.
# Idempotent: rendering is a pure function of the templates, the instance name
# and the repo path, so a re-run over an unchanged repo rewrites byte-identical
# files.
#
# Requires store-lib.sh to have been sourced and the instance's store adopted —
# mtgc_store_stamp_service is what puts the store flags into the `podman exec`
# lines, and it is a no-op for an instance in the default store (prod).
mtgc_install_units() {
    local instance="$1"
    local repo_dir="$2"
    local systemd_user_dir="$HOME/.config/systemd/user"
    local prefix ext

    mkdir -p "$systemd_user_dir"

    local units
    units="$(mtgc_units_list "$repo_dir")" || return 1

    while IFS= read -r prefix; do
        echo "==> Installing ${prefix} timer"
        for ext in service timer; do
            sed -e "s|{{INSTANCE}}|${instance}|g" \
                -e "s|{{REPO_DIR}}|${repo_dir}|g" \
                "$repo_dir/deploy/${prefix}.${ext}" \
                > "${systemd_user_dir}/${prefix}-${instance}.${ext}"
        done
        # These are rendered per instance, not %i templates, so they can carry
        # the store. Their ExecStart lines run `podman exec`; without the flags
        # an alternate-store instance's timers fire against the default store
        # and fail with "no such container". (mtgc-backup's ExecStart is
        # backup.sh, which adopts the instance itself — the stamp finds no
        # `podman ` there.)
        mtgc_store_stamp_service "${systemd_user_dir}/${prefix}-${instance}.service"
    done <<< "$units"

    # The alert unit is a systemd instance template, not a timer: its %i is the
    # name of the unit that failed, supplied by the OnFailure= that fires it.
    # Rendered per MTGC instance like everything else, so setting up a test
    # instance cannot repoint prod's alerting at a test checkout.
    echo "==> Installing mtgc-alert template"
    sed -e "s|{{INSTANCE}}|${instance}|g" \
        -e "s|{{REPO_DIR}}|${repo_dir}|g" \
        "$repo_dir/deploy/mtgc-alert@.service" \
        > "${systemd_user_dir}/mtgc-alert-${instance}@.service"

    systemctl --user daemon-reload
}
