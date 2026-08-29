# Current State

<!-- REPO-STATUS:START -->
_Last updated: 2026-08-29T08:24:43-07:00_

- Repo path: `/home/justin/.hermes/hermes-agent`
- Branch: `codex/runs-memory-control`
- Snapshot base commit: `440c81d887 fix(browser): preserve Linux real-profile logins`
- Remote: `git@github.com:NousResearch/hermes-agent.git`
- Working tree: `dirty`
- Status:
  - ` M gateway/platforms/api_server.py`
  - ` M tests/gateway/test_api_server_runs.py`
- Recent commits:
  - `440c81d887 fix(browser): preserve Linux real-profile logins`
  - `540425c2d9 docs: record Hermes auto-prune enablement`
  - `fb2b7bd807 docs: record Hermes session-store compaction`
  - `ceeffb7796 Merge remote-tracking branch 'origin/main' into justin/main`
  - `1d8946b40b fix(prompt-caching): tool-using sessions no longer 400 behind LiteLLM Anthropic proxies (#89886)`
- Key scripts:
  - `apps/bootstrap-installer` `build`: `tsc -b && vite build`
  - `apps/bootstrap-installer` `check`: `npm run typecheck && npm run lint`
  - `apps/bootstrap-installer` `dev`: `vite --host 127.0.0.1 --port 5175`
  - `apps/bootstrap-installer` `lint`: `eslint src/`
  - `apps/bootstrap-installer` `lint:fix`: `eslint src/ --fix`
  - `apps/bootstrap-installer` `preview`: `vite preview`
  - `apps/bootstrap-installer` `tauri:build`: `tauri build`
  - `apps/bootstrap-installer` `tauri:build:debug`: `tauri build --debug`
  - `apps/bootstrap-installer` `tauri:dev`: `tauri dev`
  - `apps/bootstrap-installer` `typecheck`: `tsc -p . --noEmit`
  - `apps/desktop/build/native-deps/node-pty` `build`: `tsc -b ./src/tsconfig.json`
  - `apps/desktop/build/native-deps/node-pty` `lint`: `eslint -c .eslintrc.js --ext .ts src/`
  - `apps/desktop/build/native-deps/node-pty` `posttest`: `npm run lint`
  - `apps/desktop/build/native-deps/node-pty` `test`: `cross-env NODE_ENV=test mocha -R spec --exit lib/*.test.js`
  - `apps/desktop` `build`: `node scripts/assert-root-install.mjs && node scripts/write-build-stamp.mjs && vite build && node scripts/bundle-electron-main.mjs && node scripts/stage-native-deps.mjs`
  - `apps/desktop` `builder`: `cross-env NODE_OPTIONS=--max-old-space-size=16384 node scripts/run-electron-builder.mjs`
  - `apps/desktop` `check`: `npm run check:lint && npm run test:ui && npm run test:desktop:platforms && npm run test:desktop:all`
  - `apps/desktop` `check:lint`: `npm run typecheck && npm run lint`
  - `apps/desktop` `check:test:desktop:all`: `npm run test:desktop:all`
  - `apps/desktop` `check:test:desktop:platforms`: `npm run test:desktop:platforms`
  - `apps/desktop` `check:test:ui`: `npm run test:ui`
  - `apps/desktop` `dev`: `concurrently -k "npm:dev:renderer" "npm:dev:electron"`
  - `apps/desktop` `dev:electron`: `tsc --build tsconfig.electron.json && wait-on http://127.0.0.1:5174 && node scripts/bundle-electron-main.mjs --dev && cross-env XCURSOR_SIZE=24 HERMES_DESKTOP_DEV_SERVER=http://127.0.0.1:5174 electron .`
  - `apps/desktop` `dev:fake-boot`: `cross-env HERMES_DESKTOP_BOOT_FAKE=1 HERMES_DESKTOP_BOOT_FAKE_STEP_MS=650 npm run dev`
  - `apps/desktop` `dev:mock`: `node scripts/dev-mock.mjs`
  - `apps/desktop` `dev:renderer`: `node scripts/assert-root-install.mjs && npm run clean:renderer && vite --host 127.0.0.1 --port 5174`
  - `apps/desktop` `lint`: `eslint src/ electron/`
  - `apps/desktop` `lint:fix`: `eslint src/ electron/ --fix`
  - `apps/desktop` `postbuild`: `node scripts/assert-dist-built.mjs`
  - `apps/desktop` `prebuild`: `npm run clean`
  - `apps/desktop` `prebuilder`: `node scripts/patch-electron-builder-mac-binary.mjs`
  - `apps/desktop` `preview`: `node scripts/assert-root-install.mjs && vite preview --host 127.0.0.1 --port 4174`
  - `apps/desktop` `repro:short-session-hang:test`: `node --test scripts/run-short-session-hang-repro.test.mjs`
  - `apps/desktop` `start`: `npm run build && electron .`
  - `apps/desktop` `test`: `vitest run`
  - `apps/desktop` `test:desktop`: `node scripts/test-desktop.mjs`
  - `apps/desktop` `test:desktop:all`: `node scripts/test-desktop.mjs all`
  - `apps/desktop` `test:desktop:dmg`: `node scripts/test-desktop.mjs dmg`
  - `apps/desktop` `test:desktop:existing`: `node scripts/test-desktop.mjs existing`
  - `apps/desktop` `test:desktop:fresh`: `node scripts/test-desktop.mjs fresh`
<!-- REPO-STATUS:END -->

## Direction

Hermes is the live local agent gateway on `justinsdesktop`. Local `main` is the
clean official `NousResearch/hermes-agent` branch; `justin/main` is the checked-
out production branch carrying the reviewed local patch stack; `fork/main` is
its pushable backup. Real-profile browsing is consent-enabled for the default
and Tyler profiles, and Firecrawl is the explicit web-extraction backend for
both.

## Recent Changes

- Extended the authenticated native `/v1/runs` endpoint to honor the same
  `X-Hermes-Memory: enabled|bypass` contract as `/v1/responses`. Durable runs
  now pass `skip_memory=True` into agent construction for bypassed turns, so
  background/reconnectable clients cannot accidentally recall or retain a
  sensitive request. Invalid memory-mode values fail before a run, status, or
  event queue is created.
- Reconciled the live checkout from the June upstream base onto current official
  upstream while preserving the unique memory-bypass, Hindsight durability, API
  session-lifecycle, and local runtime fixes. The old one-shot MCP and paused-job
  commits were dropped because upstream now contains stronger implementations.
- Added the official upstream real-profile browser feature and enabled
  `browser.use_real_profile: true` for both live profiles. The snapshot is a
  Hermes-owned copy under `~/.hermes/browser-profile/chrome`, not the live Chrome
  data directory; `real_profile_autoclose` remains false.
- Fixed a live Linux hang discovered during the first profile snapshot:
  `sqlite3.Connection.backup()` can retry forever despite the connection timeout
  while Chrome holds a long auth-DB transaction. Each auth DB backup is now
  bounded to ten seconds before the existing raw-copy/fail-closed path continues.
- Added `FIRECRAWL_API_KEY` from the `Social/Firecrawl/apikey` 1Password field to
  the canonical agent secret store and both mode-0600 Hermes profile env files.
  `web.extract_backend` is explicitly `firecrawl` for the default and Tyler
  profiles, preserving independent search-provider selection.
- Migrated both live configs from version 30 to 39 and installed Hermes 0.20.6,
  `hindsight-client` 0.8.6, and `firecrawl-py` 4.17.0 into the production venv.
- Replaced the vulnerable uv-managed Python 3.11.15 / SQLite 3.50.4 runtime
  with a checkout-scoped Python 3.11.16 built from the official source and
  linked by RUNPATH to a private SQLite 3.53.4 build. SQLite was configured
  with `--all` so Hermes retains FTS5/FTS4, RTREE, GEOPOLY, SESSION, DBPAGE,
  DBSTAT, CARRAY, and JSON support. The previous venv is parked beside `venv`
  as `venv.stale.runtime-1787926352-2873696-b367df54` for rollback.
- Added `scripts/hermes-local-update.sh` and the
  `~/.local/bin/hermes-local-update` launcher. The wrapper requires a clean
  `justin/main`, validates the official origin and `update_in_place`/quick-
  backup config, pre-pushes the patch stack, delegates backup/config/dependency/
  UI/restart work to Hermes's built-in updater, then verifies upstream ancestry,
  the safe SQLite+FTS5 runtime, package compatibility, both live service PIDs,
  and the final fork readback. Local `main` now tracks `origin/main` without
  patches, so the built-in updater can never mistake the patch stack for an
  upstream force-push on a same-named branch.
- The first real wrapper run merged 187 upstream commits into `justin/main`,
  refreshed Python/lazy dependencies and Node workspaces, rebuilt the web UI,
  restarted both gateway profiles, and reported both fleet members on the new
  merge commit. A second run with no pending upstream changes completed as an
  idempotent no-op and still ran every wrapper verification/readback gate.
  A final dogfood run merged seven additional upstream commits, repeated the
  restart/runtime/package/remote gates, and left `justin/main` containing
  current `origin/main` with no behind commits.
- Fixed the pending-restart catch-up race exposed by the live update wrapper.
  Hermes had restarted the two user-systemd gateways, then its manual-process
  sweep killed those fresh replacement PIDs and returned during systemd's
  five-second `Restart=always` gap. The host process scan also saw the John and
  Amanda Docker gateways under UID 10000 and emitted misleading permission
  warnings. Supplemental `/proc` discovery is now restricted to the invoking
  UID, the catch-up sweep excludes every freshly supervised PID, and the wrapper
  waits for bounded systemd recovery before performing one explicit restart and
  final interpreter readback. `--repair-services` exposes that recovery gate
  without fetching or changing source.
- Completed the opt-in v23 FTS storage migration for both live session stores.
  A stable offline window stopped the default/Tyler gateways, the Tyler
  `local-hermes-watchdog` timer, the resumable foreground optimizer, and the
  one interactive local Hermes process holding `state.db`; the separate
  UID-10000 John/Amanda Docker gateways were not touched. Fresh uncapped
  SQLite-safe snapshots were created and verified before mutation. The default
  database shrank from 4,633,100,288 to 1,914,523,648 bytes; Tyler shrank from
  360,292,352 to 56,864,768 bytes. Both public CLI checks now report the search
  index is already compact. The two gateways and watchdog timer were restored
  after verification.
- Enabled preservation-first automatic session pruning for both profiles with
  the existing 90-day inactivity window, 24-hour maintenance interval, and
  post-prune VACUUM policy. Fresh uncapped rollback snapshots were taken after
  FTS compaction and before deletion. The read-only assessment found exactly
  four eligible default sessions (all ended, unpinned, unarchived, 112–125 days
  inactive, and carrying zero messages) and zero Tyler candidates; 2,123 old
  but still-open default sessions were structurally ineligible. The first
  offline sweep removed exactly those four empty rows (11,954 → 11,950) and
  nothing from Tyler (9,795 unchanged), then both configs were set to
  `sessions.auto_prune: true`. Pinned sessions remain excluded and open sessions
  remain non-prunable.
- Repaired and fully activated consented real-profile browsing for both live
  profiles. The toggles were already true, but the prior launch was silently
  signed out: the snapshot mirrored active source `Profile 1` into `Default`
  while copied `Local State` still told Chrome to open an empty `Profile 1`, and
  agent-browser 0.31.2 forced a basic/mock keychain that cannot use Chrome's
  Linux Secret Service state. The snapshot now normalizes only the managed copy
  to `last_used: Default` and removes stale managed source-profile directories.
  Linux launches the installed stable Chromium directly on the copy with
  gnome-libsecret and an identity-bound mode-0600 PID file; normal Hermes browser
  commands still attach over CDP. Default and Tyler have independent managed
  copies/PIDs/CDP endpoints and can coexist. The user's live Chrome profile is
  never written, driven, or closed.

## Verification

- `/v1/runs` memory-control regression: the full
  `tests/gateway/test_api_server_runs.py` suite passed 27/27; focused bypass,
  invalid-value, and ordinary-start coverage passed 3/3; Ruff and
  `git diff --check` passed.
- Pre-rebase live-delta baseline: 531/531 focused tests passed before the local
  changes were committed and replayed.
- Reconciled patch stack: 276 focused tests passed in the integration worktree;
  325 focused tests passed again in a clean isolated venv containing the final
  pinned Hermes, Hindsight, and Firecrawl dependencies.
- Upstream real-profile/Firecrawl coverage: 82 selected feature tests passed.
  The final browser suite passed 74/74 after a verified red-green regression for
  the SQLite backup deadline; Ruff and `git diff --check` also passed.
- Live browser proof: default Chrome detected; snapshot completed with marker;
  snapshot parent and browser directory are owner-only mode 0700; a real-profile
  CDP endpoint came up successfully while the user's live Chrome stayed open.
- Live Firecrawl proof: authenticated credit-usage probe returned HTTP 200, then
  a real extract of `https://example.com` returned `Example Domain` with 167
  Markdown characters.
- Live runtime proof: both `hermes-gateway.service` and
  `hermes-gateway-tyler.service` are active/running on the reconciled editable
  `justin/main` checkout.
- Runtime source verification: Python 3.11.16 tarball SHA-256
  `91bcdebfdde239a003ae93738a7fce0f9230fee5c4bc2b86f6e6e8c6f98aabe8`;
  SQLite 3.53.4 autoconf tarball SHA3-256
  `454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338`.
  Hermes's own runtime predicate reports `vulnerable=False`, and the loaded
  SQLite source id is `bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc`.
- Both pre-cutover quick snapshots report zero failed/skipped databases, match
  every manifest size, and pass `PRAGMA quick_check` under SQLite 3.53.4:
  default `20260828-140645-sqlite-runtime-cutover`; Tyler
  `20260828-140942-sqlite-runtime-cutover`. Snapshot directories/files were
  tightened to modes 0700/0600.
- Runtime and database verification: the relocatable candidate passed after a
  real path rename; `uv pip check` passed for 195 packages; the SQLite/runtime
  suite passed 101 tests with one expected skip; every live default/Tyler DB
  passed `PRAGMA quick_check`; both offline FTS write-health probes returned
  `ok`; Hermes doctor reports Python 3.11.16, SQLite 3.53.4, virtualenv active,
  state.db readable, and both FTS tables. Both gateway processes load the
  private Python and `libsqlite3.so.3.53.4`, with no WAL-reset or FTS5 warning
  in the final startup window.
- Updater verification: `bash -n` passed; a reversible wrong-branch probe
  exited 1 with the intended fail-closed error; `--check` and `--plan` reported
  the exact branch/divergence/service inventory; the real update preserved all
  local commits and advanced to upstream; a second full run passed with the
  D-Bus environment deliberately removed; Python 3.11.16 / SQLite 3.53.4 /
  FTS5 passed, `uv pip check` passed for 196 packages, both systemd services
  matched the live venv interpreter, and `fork/main` read back equal to HEAD.
  The merged patch/update/browser/Hindsight/API/state focused suite passed
  322/322 tests. The updater's final parked-branch regression file then passed
  22/22 again against the exact final merge.
- Restart-race verification: both new regressions failed before the fix and
  passed after it; the expanded restart/process-discovery selection passed
  48/48. A reversible live known-bad probe stopped
  `hermes-gateway-tyler.service`, confirmed it inactive, and required
  `hermes-local-update --repair-services` to restore it on a new PID using the
  checkout's hardened interpreter. A second live run recreated
  `fleet_restart_pending` while Git was already current, exercised the exact
  catch-up branch, and completed with no permission warnings, both services
  active on fresh PIDs, Python 3.11.16 / SQLite 3.53.4 / FTS5 ready, 196
  compatible packages, zero commits behind upstream, and `fork/main` matching
  `5220a6fe81`.
- Session-storage verification: fresh rollback snapshots
  `20260829-064134-pre-fts-optimize` (default) and
  `20260829-064441-pre-fts-optimize` (Tyler) have complete manifests with zero
  failed/oversized databases, source-matching `state.db` sizes, and
  `PRAGMA quick_check=ok`. Post-migration, both live databases again passed
  `quick_check`; use the external-content FTS layout; have no optimize,
  rebuild, teardown, or legacy-trash markers; have exact message/indexed-row
  parity (271,133 default and 23,497 Tyler); and passed a real FTS `MATCH`
  probe. `optimize_fts_storage` returned `ok=true, vacuumed=true` for both and
  reclaimed 3,022,004,224 bytes total. Snapshot directories/files are mode
  0700/0600, live DBs are 0600, Hermes doctor reports zero freelist pages and
  zero-byte WALs, and both live gateway processes load Python 3.11.16 with the
  private SQLite 3.53.4 library (`wal_reset_vulnerable=false`).
- Auto-prune verification: post-compaction/pre-prune snapshots
  `20260829-070650-pre-auto-prune` (default) and
  `20260829-070754-pre-auto-prune` (Tyler) have complete manifests, zero
  failed/oversized files, owner-only modes, source-matching DB sizes, and
  `PRAGMA quick_check=ok`. The first sweep's actual deletion counts matched the
  read-only assessment exactly; pinned counts were unchanged; both stores now
  report zero 90-day candidates and durable `last_auto_prune` timestamps.
  `last_vacuum` records the immediately preceding verified FTS-compaction
  VACUUM, avoiding a redundant 1.8 GiB rewrite for four empty rows. After
  restart, both gateways reported current code, both DBs passed `quick_check`,
  and the Tyler watchdog timer was active with no auto-maintenance/SQLite error
  in the startup journal.
- Real-profile verification: the existing 74-test real-profile suite passes,
  including a red-green regression that copied `Local State` must select
  `Default`; an expanded browser/connect/cleanup selection passes 145/145.
  Live default and Tyler launches each resolved Chrome's current active source
  as `Profile 1`, copied cookies/login data/preferences into a separate
  owner-only `browser-profile/chrome`, normalized the managed last-used profile
  to `Default`, and exposed a CDP endpoint whose `DevToolsActivePort` matched
  that exact copy. Both process command lines used gnome-libsecret with neither
  mock-keychain nor basic-store flags. After Chrome account reconciliation,
  Google rendered the account control and no `Sign in` control in both copies;
  both test tabs were returned to `about:blank`. The real desktop Chrome process
  remained alive throughout, and the destructive `hermes browser close-profile`
  command was never invoked. Ubuntu `libsecret-tools` and Xvfb were installed
  for keyring diagnostics and headed-browser support; the production real-
  profile path itself is direct headless Chrome plus libsecret.

## Update Workflow

Use the installed one-command wrapper rather than running `hermes update`
directly on the patched checkout:

```bash
hermes-local-update --check  # fetch and report only
hermes-local-update --plan   # show divergence and restart plan
hermes-local-update --repair-services  # recover/verify gateways; no source update
hermes-local-update          # back up, merge, install, restart, verify, push
```

The update command fails closed if the branch is not `justin/main`, the worktree
is dirty, the origin/backup remotes are wrong, the required update config has
drifted, the merge conflicts, SQLite becomes vulnerable or loses FTS5, package
compatibility fails, either gateway is inactive/stale, or the fork readback does
not match local HEAD. It never uses `git reset --hard` or an unconditional force
push.

## Next Work

- Retain the parked vulnerable venv and the two verified state snapshots until
  the fixed runtime has completed the desired soak window. They are rollback
  assets, not active code.
- The pre-update incidental `package-lock.json` delta is preserved in stash
  `d2e1baab560ae481088b9abc4fa77f12aa545aba`; the old untracked generated
  `build/` directory remains excluded from source history.
- Retain the two verified `pre-fts-optimize` snapshots through the post-migration
  soak. The compacted default `state.db` is still about 1.8 GiB and therefore
  remains above the built-in updater's intentional 1 GiB quick-snapshot cap;
  take another uncapped/manual snapshot before any future state-schema rewrite.
- Auto-prune is enabled for both profiles. Retain the verified pre-prune
  snapshots through the initial 90-day-policy soak; the daily sweep is expected
  to no-op until another ended, unpinned session crosses the inactivity cutoff.

## Blockers

- None for real-profile browsing, Firecrawl, or the Hermes upstream cutover.

## Constraints And Gotchas

- Missing `X-Hermes-Memory` means memory enabled. Unknown values fail with HTTP
  400, and the bypass header still requires normal API authentication.
- `browser.real_profile_autoclose` is intentionally false. The snapshot path may
  copy committed auth data from an open Chrome on POSIX, but Hermes never closes
  the user's browser or drives the live profile directly.
- On Linux, do not route the consented profile copy back through an
  agent-browser-managed launch: its basic/mock keychain flags produce a valid
  CDP browser that is nevertheless signed out. Hermes owns the direct libsecret
  process via `.hermes-browser.pid`; reuse/cleanup must verify that PID's exact
  `--user-data-dir` binding before signalling it.
- Bulk prune's current upstream `archived` filter is tri-state; `None` includes
  both archived and unarchived rows. The durable automatic-preservation flag is
  `pinned`, which prune excludes unless `include_pinned=true` is explicit.
- The live main worktree retains only the old generated `build/` directory as an
  untracked artifact; do not mistake it for the editable runtime source.
- The active interpreter and SQLite library live under
  `.hermes-runtime/python/cpython-3.11.16-sqlite-3.53.4` and
  `.hermes-runtime/sqlite-3.53.4`. Do not delete either directory while `venv`
  points at that interpreter. After any future runtime rebuild, rerun
  `hermes doctor` and require SQLite 3.51.3+ (or fixed backports 3.50.7/3.44.6)
  plus FTS5 before restarting the gateways.
- Keep daily work on `justin/main`. Local `main` is intentionally the clean
  upstream branch and is not the production checkout. Direct `hermes update`
  is no longer the operator workflow; use `hermes-local-update` so the branch,
  backup, runtime, service, and remote-readback guards all run.
- Host-visible Docker gateways owned by another UID are separate runtimes and
  must never be signalled by the local checkout's manual-process cleanup.
- A stable Tyler maintenance stop also requires temporarily stopping
  `local-hermes-watchdog.timer` and `local-hermes-watchdog.service`; otherwise
  the watchdog correctly relaunches the gateway while its database is offline.
- `sessions.auto_prune` is permanent deletion, not archive rotation: it deletes
  only ended sessions inactive for 90 days, includes old archived rows, excludes
  pinned rows, and can never select open sessions. The separate
  `hermes-session-maintenance` archive/receipt job is not its prerequisite or
  rollback mechanism; use the verified uncapped snapshots for rollback.
- Aivex Portal is retired. Keep technical continuity here, never in Portal.
