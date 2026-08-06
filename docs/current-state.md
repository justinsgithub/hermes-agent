# Current State

<!-- REPO-STATUS:START -->
_Last updated: 2026-08-06T12:53:08-07:00_

- Repo path: `/home/justin/.hermes/hermes-agent`
- Branch: `main`
- Snapshot base commit: `c063ee8aa feat(api): support explicit memory bypass`
- Remote: `git@github.com:NousResearch/hermes-agent.git`
- Working tree: `dirty`
- Status:
  - ` M AGENTS.md`
  - ` M agent/subdirectory_hints.py`
  - ` M gateway/run.py`
  - ` M gateway/stream_consumer.py`
  - ` M tests/agent/test_subdirectory_hints.py`
  - ` M tests/gateway/test_restart_notification.py`
- Recent commits:
  - `c063ee8aa feat(api): support explicit memory bypass`
  - `c9a861294 fix(cli): wait for MCP discovery in one-shot mode`
  - `5ff11a689 feat(cli): /timestamps command + timestamps in /history (#50506)`
  - `b9b4756ab fix dashboard chat session titles`
  - `5dae502b8 Address email pairing review feedback`
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

- `c063ee8aa` adds strict `X-Hermes-Memory: enabled|bypass` handling to
  `POST /v1/responses` and threads `skip_memory` into `AIAgent` construction.
- `/home/justin/.hermes/scripts/local-hermes-watchdog.sh` now sends the explicit
  bypass header and uses a unique response tempfile. The three-minute watchdog
  continues real model generation but no longer invokes Hindsight.

## Verification

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

- Monitor the watchdog and Hindsight request counts over the next daily window;
  no implementation follow-up is currently required.

## Blockers

- None recorded.

## Constraints And Gotchas

- Missing `X-Hermes-Memory` means memory enabled. Unknown values fail with HTTP
  400, and the bypass header still requires normal API authentication.
- The live main worktree contains unrelated pre-existing edits; preserve them.
- Aivex Portal is retired. Keep technical continuity here, never in Portal.
