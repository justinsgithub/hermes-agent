#!/usr/bin/env bash
# Update Justin's maintained Hermes patch branch with the official upstream.
#
# This is intentionally a thin guard around Hermes's own updater. Hermes owns
# backups, config migration, dependency synchronization, runtime repair, and
# fleet restart. This wrapper makes the branch/remote contract explicit,
# preserves local work outside the clean update window, and verifies the live
# result before pushing the updated patch stack.

set -euo pipefail

repo="${HERMES_REPO:-$HOME/.hermes/hermes-agent}"
patch_branch="${HERMES_PATCH_BRANCH:-justin/main}"
target_branch="${HERMES_TARGET_BRANCH:-main}"
backup_remote="${HERMES_BACKUP_REMOTE:-fork}"
backup_ref="${HERMES_BACKUP_REF:-main}"
mode="update"
service_settle_seconds="${HERMES_SERVICE_SETTLE_SECONDS:-15}"
service_recovery_seconds="${HERMES_SERVICE_RECOVERY_SECONDS:-30}"
autostash_ref=""
autostash_active=0
autostash_restore_attempted=0

usage() {
    printf '%s\n' \
        'Usage: hermes-local-update [--check|--plan|--repair-services]' \
        '' \
        '  no argument  Back up, update, verify, restart, and push.' \
        '  --check      Fetch and report upstream divergence only.' \
        '  --plan       Show divergence and Hermes restart plan only.' \
        '  --repair-services  Recover and verify the two local gateways only.'
}

log() {
    printf '[hermes-local-update] %s\n' "$*"
}

die() {
    printf '[hermes-local-update] ERROR: %s\n' "$*" >&2
    exit 1
}

preserve_local_changes() {
    local previous_stash stash_rc current_stash

    test -n "$(git status --porcelain --untracked-files=normal)" || return 0

    previous_stash="$(git rev-parse --verify --quiet refs/stash || true)"
    log "local changes detected; snapshotting them before the clean update window"

    # Reuse Hermes's tested autostash implementation. It captures tracked and
    # untracked work, verifies that a new stash object exists, and handles the
    # permission-denied edge where Git saves a complete stash but cannot remove
    # an untracked path from the checkout.
    set +e
    "$python_bin" - "$repo" <<'PY'
import sys
from pathlib import Path

from hermes_cli import main as hermes_main

stash_ref = hermes_main._stash_local_changes_if_needed(
    ["git"], Path(sys.argv[1])
)
if not stash_ref:
    raise SystemExit("dirty worktree produced no Hermes autostash")
PY
    stash_rc=$?
    set -e

    current_stash="$(git rev-parse --verify --quiet refs/stash || true)"
    if test -n "$current_stash" && test "$current_stash" != "$previous_stash"; then
        autostash_ref="$current_stash"
        autostash_active=1
    fi

    test "$stash_rc" -eq 0 || die \
        "could not snapshot local changes; the checkout was not updated"
    test "$autostash_active" -eq 1 || die \
        "Hermes reported a snapshot but no new stash could be verified"
    test -z "$(git status --porcelain --untracked-files=normal)" || die \
        "local changes are preserved in stash $autostash_ref, but the checkout could not be made clean"

    log "local changes preserved in stash ${autostash_ref:0:12}"
}

restore_local_changes() {
    local restore_rc

    test "$autostash_active" -eq 1 || return 0
    autostash_restore_attempted=1

    if test "$(git branch --show-current)" != "$patch_branch"; then
        return 1
    fi
    if test -n "$(git status --porcelain --untracked-files=normal)"; then
        return 1
    fi

    log "restoring the preserved local changes"
    set +e
    "$python_bin" - "$repo" "$autostash_ref" <<'PY'
import sys
from pathlib import Path

from hermes_cli import main as hermes_main

restored = hermes_main._restore_stashed_changes(
    ["git"], Path(sys.argv[1]), sys.argv[2], prompt_user=False
)
raise SystemExit(0 if restored else 1)
PY
    restore_rc=$?
    set -e

    if test "$restore_rc" -eq 0; then
        autostash_active=0
        log "local changes restored"
        return 0
    fi
    return 1
}

restore_local_changes_on_exit() {
    local exit_code=$?

    trap - EXIT
    if test "$autostash_active" -eq 1 && \
            test "$autostash_restore_attempted" -eq 0; then
        log "update stopped before local changes were restored; attempting recovery"
        if ! restore_local_changes; then
            printf '%s\n' \
                "[hermes-local-update] ERROR: local changes remain safely preserved in stash $autostash_ref" \
                '[hermes-local-update] Inspect git status before applying that stash manually.' >&2
            if test "$exit_code" -eq 0; then
                exit_code=1
            fi
        fi
    elif test "$autostash_active" -eq 1; then
        printf '%s\n' \
            "[hermes-local-update] ERROR: local changes remain safely preserved in stash $autostash_ref" \
            '[hermes-local-update] Inspect git status before applying that stash manually.' >&2
    fi
    exit "$exit_code"
}

case "${1:-}" in
    '') ;;
    --check) mode="check" ;;
    --plan) mode="plan" ;;
    --repair-services) mode="repair-services" ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

for command in git flock systemctl; do
    command -v "$command" >/dev/null 2>&1 || die "required command not found: $command"
done

# Tool shells and unattended launchers often omit the user-session D-Bus
# variables even though the systemd user manager is healthy. Bind the canonical
# local bus explicitly so the final service readback tests the real units rather
# than failing on shell environment drift.
user_runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export XDG_RUNTIME_DIR="$user_runtime_dir"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$user_runtime_dir/bus}"
test -S "$user_runtime_dir/bus" || die "systemd user bus is unavailable: $user_runtime_dir/bus"

test -d "$repo/.git" || die "not a Git checkout: $repo"
cd "$repo"

hermes_bin="${HERMES_BIN:-$repo/venv/bin/hermes}"
python_bin="${HERMES_PYTHON_BIN:-$repo/venv/bin/python}"
test -x "$hermes_bin" || die "Hermes CLI is not executable: $hermes_bin"
test -x "$python_bin" || die "Hermes Python is not executable: $python_bin"

wait_for_service_runtime() {
    local service="$1"
    local timeout_seconds="$2"
    local deadline=$((SECONDS + timeout_seconds))
    local pid process_exe

    while (( SECONDS <= deadline )); do
        if systemctl --user is-active --quiet "$service"; then
            pid="$(systemctl --user show "$service" -p MainPID --value)"
            if test -n "$pid" && test "$pid" != "0" && test -r "/proc/$pid/exe"; then
                process_exe="$(readlink -f "/proc/$pid/exe")"
                if test "$process_exe" = "$(readlink -f "$python_bin")"; then
                    return 0
                fi
            fi
        fi
        sleep 1
    done
    return 1
}

ensure_gateway_services() {
    local service
    for service in hermes-gateway.service hermes-gateway-tyler.service; do
        # systemd Restart=always intentionally creates a brief inactive gap.
        # Let that bounded self-recovery settle before taking over.
        if ! wait_for_service_runtime "$service" "$service_settle_seconds"; then
            log "$service did not settle; recovering it through user systemd"
            systemctl --user reset-failed "$service" >/dev/null 2>&1 || true
            systemctl --user restart "$service" || die \
                "could not restart $service"
            wait_for_service_runtime "$service" "$service_recovery_seconds" || die \
                "$service did not become healthy on the live venv after recovery"
        fi
        pid="$(systemctl --user show "$service" -p MainPID --value)"
        log "$service active on PID $pid"
    done
}

mkdir -p "$repo/.hermes-runtime"
exec 9>"$repo/.hermes-runtime/local-update.lock"
flock -n 9 || die "another local Hermes update is already running"

if test "$mode" = "repair-services"; then
    ensure_gateway_services
    log "gateway service repair and verification complete"
    exit 0
fi

current_branch="$(git branch --show-current)"
test "$current_branch" = "$patch_branch" || die \
    "checkout must be on '$patch_branch' (currently '${current_branch:-detached HEAD}')"

origin_url="$(git remote get-url origin 2>/dev/null || true)"
case "$origin_url" in
    *NousResearch/hermes-agent|*NousResearch/hermes-agent.git) ;;
    *) die "origin is not the official NousResearch/hermes-agent remote: $origin_url" ;;
esac

git remote get-url "$backup_remote" >/dev/null 2>&1 || die \
    "backup remote '$backup_remote' is not configured"

log "fetching official upstream"
git fetch origin "$target_branch"

ahead="$(git rev-list --count "origin/$target_branch..HEAD")"
behind="$(git rev-list --count "HEAD..origin/$target_branch")"
log "branch=$patch_branch upstream=origin/$target_branch ahead=$ahead behind=$behind"

if test "$mode" = "check"; then
    "$hermes_bin" update --check --branch "$target_branch"
    exit 0
fi

if test "$mode" = "plan"; then
    "$hermes_bin" update --plan --branch "$target_branch"
    exit 0
fi

config_path="${HERMES_HOME:-$HOME/.hermes}/config.yaml"
strategy="$("$python_bin" -c 'import pathlib,sys,yaml; c=yaml.safe_load(pathlib.Path(sys.argv[1]).read_text()) or {}; print((c.get("updates") or {}).get("parked_branch_strategy", ""))' "$config_path")"
backup_mode="$("$python_bin" -c 'import pathlib,sys,yaml; c=yaml.safe_load(pathlib.Path(sys.argv[1]).read_text()) or {}; print((c.get("updates") or {}).get("pre_update_backup", ""))' "$config_path")"
test "$strategy" = "update_in_place" || die \
    "updates.parked_branch_strategy must be update_in_place (found '$strategy')"
test "$backup_mode" = "quick" || die \
    "updates.pre_update_backup must be quick (found '$backup_mode')"

before_sha="$(git rev-parse HEAD)"

trap restore_local_changes_on_exit EXIT
preserve_local_changes

log "pushing the pre-update patch stack to $backup_remote/$backup_ref"
git push "$backup_remote" "HEAD:$backup_ref"

log "running Hermes's guarded updater"
"$hermes_bin" update --branch "$target_branch" --yes

test "$(git branch --show-current)" = "$patch_branch" || die \
    "updater left the checkout on the wrong branch"
test -z "$(git status --porcelain --untracked-files=normal)" || die \
    "updater left a dirty working tree"
git merge-base --is-ancestor "origin/$target_branch" HEAD || die \
    "updated branch does not contain origin/$target_branch"

log "verifying Python, SQLite, and FTS5"
"$python_bin" -c '
import sqlite3
import sys
from hermes_cli.sqlite_runtime import probe_sqlite_runtime

runtime = probe_sqlite_runtime(sys.executable)
if runtime is None or runtime.wal_reset_vulnerable:
    raise SystemExit("SQLite runtime is missing or WAL-reset vulnerable")
db = sqlite3.connect(":memory:")
try:
    db.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    db.execute("INSERT INTO t VALUES (?)", ("hermesready",))
    assert db.execute(
        "SELECT x FROM t WHERE t MATCH ?", ("hermesready",)
    ).fetchone()[0] == "hermesready"
finally:
    db.close()
print(f"Python {sys.version.split()[0]} / SQLite {sqlite3.sqlite_version} / FTS5 ready")
'

uv_bin="$(command -v uv 2>/dev/null || true)"
if test -z "$uv_bin" && test -x "$HOME/.hermes/bin/uv"; then
    uv_bin="$HOME/.hermes/bin/uv"
fi
test -n "$uv_bin" || die "uv is unavailable for the dependency compatibility check"
"$uv_bin" pip check --python "$python_bin"

ensure_gateway_services

log "pushing the verified patch stack to $backup_remote/$backup_ref"
git push "$backup_remote" "HEAD:$backup_ref"
remote_sha="$(git ls-remote "$backup_remote" "refs/heads/$backup_ref" | awk '{print $1}')"
test "$remote_sha" = "$(git rev-parse HEAD)" || die \
    "$backup remote readback does not match local HEAD"

after_sha="$(git rev-parse HEAD)"
restore_local_changes || die \
    "update completed, but local changes could not be reapplied automatically; they remain safe in stash $autostash_ref"
trap - EXIT
log "complete before=${before_sha:0:10} after=${after_sha:0:10} backup=$backup_remote/$backup_ref"
