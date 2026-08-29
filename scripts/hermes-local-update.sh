#!/usr/bin/env bash
# Update Justin's maintained Hermes patch branch with the official upstream.
#
# This is intentionally a thin guard around Hermes's own updater. Hermes owns
# backups, config migration, dependency synchronization, runtime repair, and
# fleet restart. This wrapper makes the branch/remote contract explicit and
# verifies the live result before pushing the updated patch stack.

set -euo pipefail

repo="${HERMES_REPO:-$HOME/.hermes/hermes-agent}"
patch_branch="${HERMES_PATCH_BRANCH:-justin/main}"
target_branch="${HERMES_TARGET_BRANCH:-main}"
backup_remote="${HERMES_BACKUP_REMOTE:-fork}"
backup_ref="${HERMES_BACKUP_REF:-main}"
mode="update"

usage() {
    printf '%s\n' \
        'Usage: hermes-local-update [--check|--plan]' \
        '' \
        '  no argument  Back up, update, verify, restart, and push.' \
        '  --check      Fetch and report upstream divergence only.' \
        '  --plan       Show divergence and Hermes restart plan only.'
}

log() {
    printf '[hermes-local-update] %s\n' "$*"
}

die() {
    printf '[hermes-local-update] ERROR: %s\n' "$*" >&2
    exit 1
}

case "${1:-}" in
    '') ;;
    --check) mode="check" ;;
    --plan) mode="plan" ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

for command in git flock systemctl; do
    command -v "$command" >/dev/null 2>&1 || die "required command not found: $command"
done

test -d "$repo/.git" || die "not a Git checkout: $repo"
cd "$repo"

hermes_bin="${HERMES_BIN:-$repo/venv/bin/hermes}"
python_bin="$repo/venv/bin/python"
test -x "$hermes_bin" || die "Hermes CLI is not executable: $hermes_bin"
test -x "$python_bin" || die "Hermes Python is not executable: $python_bin"

mkdir -p "$repo/.hermes-runtime"
exec 9>"$repo/.hermes-runtime/local-update.lock"
flock -n 9 || die "another local Hermes update is already running"

current_branch="$(git branch --show-current)"
test "$current_branch" = "$patch_branch" || die \
    "checkout must be on '$patch_branch' (currently '${current_branch:-detached HEAD}')"

worktree_status="$(git status --porcelain --untracked-files=normal)"
test -z "$worktree_status" || die \
    "working tree is dirty; commit or stash it before updating"

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
"$repo/venv/bin/python" -c '
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
"$uv_bin" pip check --python "$repo/venv/bin/python"

for service in hermes-gateway.service hermes-gateway-tyler.service; do
    systemctl --user is-active --quiet "$service" || die "$service is not active"
    pid="$(systemctl --user show "$service" -p MainPID --value)"
    test "$pid" != "0" || die "$service has no main process"
    process_exe="$(readlink -f "/proc/$pid/exe")"
    live_exe="$(readlink -f "$repo/venv/bin/python")"
    test "$process_exe" = "$live_exe" || die \
        "$service still runs $process_exe instead of $live_exe"
done

log "pushing the verified patch stack to $backup_remote/$backup_ref"
git push "$backup_remote" "HEAD:$backup_ref"
remote_sha="$(git ls-remote "$backup_remote" "refs/heads/$backup_ref" | awk '{print $1}')"
test "$remote_sha" = "$(git rev-parse HEAD)" || die \
    "$backup remote readback does not match local HEAD"

after_sha="$(git rev-parse HEAD)"
log "complete before=${before_sha:0:10} after=${after_sha:0:10} backup=$backup_remote/$backup_ref"
