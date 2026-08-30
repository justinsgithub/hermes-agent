"""Behavioral regression coverage for ``scripts/hermes-local-update.sh``."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "hermes-local-update.sh"


def _run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = _run("git", *args, cwd=cwd)
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed ({result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)


@pytest.fixture
def updater_repo(tmp_path: Path):
    origin = tmp_path / "NousResearch" / "hermes-agent.git"
    fork = tmp_path / "fork.git"
    seed = tmp_path / "seed"
    repo = tmp_path / "checkout"
    hermes_home = tmp_path / "hermes-home"
    fake_bin = tmp_path / "fake-bin"
    runtime_dir = tmp_path / "runtime"

    origin.parent.mkdir(parents=True)
    _git(tmp_path, "init", "--bare", str(origin))
    _git(tmp_path, "init", "--bare", str(fork))
    _git(tmp_path, "init", str(seed))
    _git(seed, "config", "user.name", "Updater Test")
    _git(seed, "config", "user.email", "updater-test@example.invalid")
    (seed / ".gitignore").write_text("venv/\n.hermes-runtime/\n")
    (seed / "tracked.txt").write_text("base\n")
    (seed / "upstream.txt").write_text("upstream-v1\n")
    _git(seed, "add", ".gitignore", "tracked.txt", "upstream.txt")
    _git(seed, "commit", "-m", "base")
    _git(seed, "branch", "-M", "main")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "main")
    _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")

    _git(tmp_path, "clone", str(origin), str(repo))
    _git(repo, "config", "user.name", "Updater Test")
    _git(repo, "config", "user.email", "updater-test@example.invalid")
    _git(repo, "switch", "-c", "justin/main")
    (repo / "local-patch.txt").write_text("committed local patch\n")
    _git(repo, "add", "local-patch.txt")
    _git(repo, "commit", "-m", "local patch")
    _git(repo, "remote", "add", "fork", str(fork))

    (seed / "upstream.txt").write_text("upstream-v2\n")
    _git(seed, "add", "upstream.txt")
    _git(seed, "commit", "-m", "upstream update")
    _git(seed, "push", "origin", "main")

    fake_hermes = fake_bin / "hermes"
    _write_executable(
        fake_hermes,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ " $* " == *" --check "* ]]; then
    printf '%s\n' 'fake check complete'
elif [[ " $* " == *" --plan "* ]]; then
    printf '%s\n' 'fake plan complete'
elif [[ "${FAKE_HERMES_FAIL:-0}" == "1" ]]; then
    printf '%s\n' 'forced updater failure' >&2
    exit 23
else
    git merge --no-edit origin/main
fi
""",
    )

    _write_executable(
        fake_bin / "systemctl",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--user" ]]; then shift; fi
case "${1:-}" in
    is-active) exit 0 ;;
    show) printf '%s\n' "$FAKE_SERVICE_PID" ;;
    reset-failed|restart) exit 0 ;;
    *) exit 0 ;;
esac
""",
    )
    _write_executable(fake_bin / "uv", "#!/usr/bin/env bash\nexit 0\n")

    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "updates:\n"
        "  parked_branch_strategy: update_in_place\n"
        "  pre_update_backup: quick\n"
        "  non_interactive_local_changes: stash\n"
    )

    runtime_dir.mkdir()
    bus_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    bus_socket.bind(str(runtime_dir / "bus"))
    bus_socket.listen(1)
    service_process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "HERMES_REPO": str(repo),
            "HERMES_BIN": str(fake_hermes),
            "HERMES_PYTHON_BIN": sys.executable,
            "HERMES_HOME": str(hermes_home),
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir / 'bus'}",
            "FAKE_SERVICE_PID": str(service_process.pid),
            "HERMES_SERVICE_SETTLE_SECONDS": "1",
            "HERMES_SERVICE_RECOVERY_SECONDS": "1",
        }
    )

    try:
        yield repo, seed, env
    finally:
        service_process.terminate()
        service_process.wait(timeout=10)
        bus_socket.close()


@pytest.mark.parametrize(
    ("mode", "marker"),
    [("--check", "fake check complete"), ("--plan", "fake plan complete")],
)
def test_read_only_modes_allow_dirty_tree_and_leave_it_untouched(
    updater_repo, mode: str, marker: str
):
    repo, _seed, env = updater_repo
    (repo / "tracked.txt").write_text("local edit\n")

    result = _run(str(SCRIPT), mode, cwd=repo, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert marker in result.stdout
    assert "working tree is dirty" not in result.stderr
    assert (repo / "tracked.txt").read_text() == "local edit\n"
    assert "tracked.txt" in _git(repo, "status", "--short").stdout
    assert _git(repo, "stash", "list").stdout == ""


def test_update_snapshots_then_restores_dirty_tree(updater_repo):
    repo, _seed, env = updater_repo
    (repo / "tracked.txt").write_text("local edit\n")
    (repo / "local-patch.txt").write_text("staged local edit\n")
    _git(repo, "add", "local-patch.txt")
    (repo / "untracked-note.txt").write_text("untracked local edit\n")

    result = _run(str(SCRIPT), cwd=repo, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "local changes preserved in stash" in result.stdout
    assert "local changes restored" in result.stdout
    assert "working tree is dirty" not in result.stderr
    assert (repo / "tracked.txt").read_text() == "local edit\n"
    assert (repo / "local-patch.txt").read_text() == "staged local edit\n"
    assert (repo / "untracked-note.txt").read_text() == "untracked local edit\n"
    assert (repo / "upstream.txt").read_text() == "upstream-v2\n"
    assert _git(repo, "stash", "list").stdout == ""
    restored_tracked = set(_git(repo, "diff", "--name-only").stdout.splitlines())
    assert restored_tracked == {"local-patch.txt", "tracked.txt"}
    assert _git(repo, "diff", "--cached", "--name-only").stdout.strip() == ""
    assert "untracked-note.txt" in _git(repo, "status", "--short").stdout
    assert _git(repo, "merge-base", "--is-ancestor", "origin/main", "HEAD").returncode == 0
    local_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    remote_head = _git(repo, "ls-remote", "fork", "refs/heads/main").stdout.split()[0]
    assert remote_head == local_head


def test_failed_update_restores_snapshot_before_exit(updater_repo):
    repo, _seed, env = updater_repo
    (repo / "tracked.txt").write_text("local edit\n")
    env["FAKE_HERMES_FAIL"] = "1"

    result = _run(str(SCRIPT), cwd=repo, env=env)

    assert result.returncode == 23
    assert "update stopped before local changes were restored" in result.stdout
    assert "local changes restored" in result.stdout
    assert (repo / "tracked.txt").read_text() == "local edit\n"
    assert _git(repo, "stash", "list").stdout == ""


def test_restore_conflict_keeps_exact_recovery_stash(updater_repo):
    repo, seed, env = updater_repo
    (repo / "tracked.txt").write_text("local edit\n")
    (seed / "tracked.txt").write_text("upstream edit\n")
    _git(seed, "add", "tracked.txt")
    _git(seed, "commit", "-m", "conflicting upstream edit")
    _git(seed, "push", "origin", "main")

    result = _run(str(SCRIPT), cwd=repo, env=env)

    assert result.returncode == 1
    assert "could not be reapplied automatically" in result.stderr
    assert "remain safely preserved in stash" in result.stderr
    assert (repo / "tracked.txt").read_text() == "upstream edit\n"
    assert _git(repo, "status", "--porcelain").stdout == ""
    stash_list = _git(repo, "stash", "list", "--format=%H %gs").stdout
    assert "hermes-update-autostash" in stash_list
    stash_ref = stash_list.split()[0]
    stashed_file = _git(repo, "show", f"{stash_ref}:tracked.txt").stdout
    assert stashed_file == "local edit\n"
