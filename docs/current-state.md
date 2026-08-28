# Current State

<!-- REPO-STATUS:START -->
_Last updated: 2026-08-20T08:48:03-07:00_

- Repo path: `/home/justin/.hermes/hermes-agent`
- Branch: `main`
- Snapshot base commit: `4e2d53f50 fix(cron): reject paused legacy jobs`
- Remote: `git@github.com:NousResearch/hermes-agent.git`
- Working tree: `dirty`
- Status:
  - ` M AGENTS.md`
  - ` M agent/subdirectory_hints.py`
  - ` M gateway/platforms/api_server.py`
  - ` M gateway/run.py`
  - ` M gateway/stream_consumer.py`
  - ` M hermes_state.py`
  - ` M plugins/memory/hindsight/README.md`
  - ` M plugins/memory/hindsight/__init__.py`
  - ` M plugins/memory/hindsight/contract.py`
  - ` M plugins/memory/hindsight/deployment-profiles.json`
  - ` M tests/agent/test_subdirectory_hints.py`
  - ` M tests/gateway/test_api_server.py`
  - ` M tests/gateway/test_restart_notification.py`
  - ` M tests/plugins/memory/test_hindsight_memory_quality.py`
  - ` M tests/test_hermes_state.py`
  - `?? build/`
- Recent commits:
  - `4e2d53f50 fix(cron): reject paused legacy jobs`
  - `1f21bb951 feat(memory): harden Hindsight retention and recall`
  - `8db2b5d23 docs: record Hermes memory bypass state`
  - `c063ee8aa feat(api): support explicit memory bypass`
  - `c9a861294 fix(cli): wait for MCP discovery in one-shot mode`
- Key scripts:
  - `apps/bootstrap-installer` `build`: `tsc -b && vite build`
  - `apps/bootstrap-installer` `dev`: `vite --host 127.0.0.1 --port 5175`
  - `apps/bootstrap-installer` `preview`: `vite preview`
  - `apps/bootstrap-installer` `tauri:build`: `tauri build`
  - `apps/bootstrap-installer` `tauri:build:debug`: `tauri build --debug`
  - `apps/bootstrap-installer` `tauri:dev`: `tauri dev`
  - `apps/bootstrap-installer` `typecheck`: `tsc -p . --noEmit`
  - `apps/desktop/build/native-deps/node-pty` `build`: `tsc -b ./src/tsconfig.json`
  - `apps/desktop/build/native-deps/node-pty` `lint`: `eslint -c .eslintrc.js --ext .ts src/`
  - `apps/desktop/build/native-deps/node-pty` `posttest`: `npm run lint`
  - `apps/desktop/build/native-deps/node-pty` `test`: `cross-env NODE_ENV=test mocha -R spec --exit lib/*.test.js`
  - `apps/desktop` `build`: `node scripts/assert-root-install.cjs && node scripts/write-build-stamp.cjs && node scripts/stage-native-deps.cjs && tsc -b && vite build && npm run postbuild`
  - `apps/desktop` `builder`: `cross-env NODE_OPTIONS=--max-old-space-size=16384 node scripts/run-electron-builder.cjs`
  - `apps/desktop` `dev`: `concurrently -k "npm:dev:renderer" "npm:dev:electron"`
  - `apps/desktop` `dev:electron`: `wait-on http://127.0.0.1:5174 && cross-env XCURSOR_SIZE=24 HERMES_DESKTOP_DEV_SERVER=http://127.0.0.1:5174 electron .`
  - `apps/desktop` `dev:fake-boot`: `cross-env HERMES_DESKTOP_BOOT_FAKE=1 HERMES_DESKTOP_BOOT_FAKE_STEP_MS=650 npm run dev`
  - `apps/desktop` `dev:renderer`: `node scripts/assert-root-install.cjs && vite --host 127.0.0.1 --port 5174`
  - `apps/desktop` `lint`: `eslint src/ electron/`
  - `apps/desktop` `lint:fix`: `eslint src/ electron/ --fix`
  - `apps/desktop` `postbuild`: `node scripts/assert-dist-built.cjs`
  - `apps/desktop` `prebuilder`: `node scripts/patch-electron-builder-mac-binary.cjs`
  - `apps/desktop` `preview`: `node scripts/assert-root-install.cjs && vite preview --host 127.0.0.1 --port 4174`
  - `apps/desktop` `start`: `npm run build && electron .`
  - `apps/desktop` `test:desktop`: `node scripts/test-desktop.mjs`
  - `apps/desktop` `test:desktop:all`: `node scripts/test-desktop.mjs all`
  - `apps/desktop` `test:desktop:dmg`: `node scripts/test-desktop.mjs dmg`
  - `apps/desktop` `test:desktop:existing`: `node scripts/test-desktop.mjs existing`
  - `apps/desktop` `test:desktop:fresh`: `node scripts/test-desktop.mjs fresh`
  - `apps/desktop` `test:desktop:nsis`: `node scripts/test-desktop.mjs nsis`
  - `apps/desktop` `test:desktop:platforms`: `node --test electron/bootstrap-platform.test.cjs electron/hardening.test.cjs electron/backend-env.test.cjs electron/backend-probes.test.cjs electron/backend-ready.test.cjs electron/bootstrap-runner.test.cjs electron/connection-config.test.cjs electron/dashboard-token.test.cjs electron/gateway-ws-probe.test.cjs electron/oauth-net-request.test.cjs electron/desktop-uninstall.test.cjs electron/session-windows.test.cjs electron/link-title-window.test.cjs electron/workspace-cwd.test.cjs electron/fs-read-dir.test.cjs electron/git-root.test.cjs electron/windows-child-process.test.cjs electron/update-remote.test.cjs electron/update-rebuild.test.cjs electron/update-marker.test.cjs electron/update-relaunch.test.cjs electron/windows-user-env.test.cjs`
  - `apps/desktop` `test:ui`: `vitest run --environment jsdom`
  - `apps/desktop` `typecheck`: `tsc -p . --noEmit`
  - `apps/desktop/release/linux-unpacked/resources/native-deps/node-pty` `build`: `tsc -b ./src/tsconfig.json`
  - `apps/desktop/release/linux-unpacked/resources/native-deps/node-pty` `lint`: `eslint -c .eslintrc.js --ext .ts src/`
  - `apps/desktop/release/linux-unpacked/resources/native-deps/node-pty` `posttest`: `npm run lint`
  - `apps/desktop/release/linux-unpacked/resources/native-deps/node-pty` `test`: `cross-env NODE_ENV=test mocha -R spec --exit lib/*.test.js`
  - `apps/shared` `typecheck`: `tsc -p . --noEmit`
  - `plugins/platforms/photon/sidecar` `start`: `node index.mjs`
  - `scripts/whatsapp-bridge` `start`: `node bridge.js`
  - `ui-tui` `build`: `node scripts/build.mjs`
<!-- REPO-STATUS:END -->

## Direction

Hermes is the live local agent gateway. API callers use the normal memory-enabled
path by default; explicitly authenticated synthetic generation probes may opt out
of long-term recall/retain without bypassing generation or API authentication.

## Recent Changes

- The built-in cron due-job path now fails closed on `state=paused` even when a
  malformed legacy row still says `enabled=true`, matching the external-fire
  claim path. The live inconsistent watchdog row was normalized through the
  canonical `hermes cron pause` transaction (`enabled=false`, `state=paused`)
  before both gateways were gracefully reloaded.
- Hermes API sessions are now request-scoped: a chained session is reopened for
  the turn and finalized as `request_complete` or `request_error` afterward.
  Retention now uses last message activity, never prunes `archived=1` sessions,
  and can finalize abandoned non-interactive sessions after 24 hours.
- Weekly maintenance lives outside the repo at
  `/home/justin/.agents/scripts/hermes-session-maintenance.sh`. It stops the
  owning gateway, makes and integrity-checks a compressed SQLite backup, then
  finalizes stale sessions, prunes inactive unpinned sessions older than 30
  days, vacuums, and restarts the gateway. The user timer is enabled for Sunday
  04:00 local.
- `c063ee8aa` adds strict `X-Hermes-Memory: enabled|bypass` handling to
  `POST /v1/responses` and threads `skip_memory` into `AIAgent` construction.
- `/home/justin/.hermes/scripts/local-hermes-watchdog.sh` now sends the explicit
  bypass header and uses a unique response tempfile. The three-minute watchdog
  continues real model generation but no longer invokes Hindsight.

## Verification

- The paused-row regression failed before the source fix (1 failed / 92 passed),
  then the focused job tests passed 99/99. The complete cron subsystem passed
  510/510 across 22 files, and `git diff --check` passed for the two-file patch.
  Both `hermes-gateway.service` and `hermes-gateway-tyler.service` changed PID
  under drain-aware reload, returned active/running, and wrote fresh cron ticker
  heartbeats. The paused job's `last_run_at` remained at 07:36 PDT after its
  former 08:06 due time.
- The 2026-08-14 maintenance pass reduced the main state database from 34,483
  sessions / 391,678 messages to 15,121 / 272,267. It finalized 18,429 stale
  request-scoped sessions, pruned 19,362 inactive ended sessions, and vacuumed
  the database from 7.8 GB to 4.3 GB. The pre-prune SQLite archive passed
  `quick_check`, zstd integrity, and SHA receipt verification.
- Full `tests/test_hermes_state.py` plus `tests/gateway/test_api_server.py`:
  455 passed. Python compilation and `git diff --check` passed.
- The editable install used by both local gateways resolves `hermes_state.py`
  and `gateway/platforms/api_server.py` from this worktree. Both gateways
  restarted active. A real authenticated `POST /v1/responses` returned HTTP
  200 and left zero open API sessions; the persisted row ended with
  `request_complete` and two messages. A subsequent real Tyler watchdog cycle
  also created and closed its session as `request_complete`; both maintenance
  dry-runs then reported zero stale open API sessions.
- `scripts/run_tests.sh tests/gateway/test_api_server.py`: 171 passed.
- `systemctl --user restart hermes-gateway.service`: active with the new source.
- `systemctl --user start local-hermes-watchdog.service`: exit 0; later timer run
  at 2026-08-06 12:51:50 PDT also exited 0.
- Business Hindsight telemetry after that timer: zero new documents, memory units,
  or LLM requests attributable to the watchdog.
- Same-window ordinary authenticated API control returned HTTP 200 and produced
  successful retain/consolidation requests; its exact validation records were
  removed after proof.

## Next Work

- Monitor the weekly maintenance receipt and API open-session count. The
  retention defect itself has no known implementation follow-up.
- Monitor the watchdog and Hindsight request counts over the next daily window.
- Keep pause/resume mutations on the locked job-store API; direct JSON edits can
  still create inconsistent legacy rows, which are now safely ignored.

## Blockers

- None recorded.

## Constraints And Gotchas

- Missing `X-Hermes-Memory` means memory enabled. Unknown values fail with HTTP
  400, and the bypass header still requires normal API authentication.
- The live main worktree contains unrelated pre-existing edits; preserve them.
- Aivex Portal is retired. Keep technical continuity here, never in Portal.
