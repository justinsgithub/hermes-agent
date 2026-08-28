# Current State

<!-- REPO-STATUS:START -->
_Last updated: 2026-08-28T07:21:51-07:00_

- Repo path: `/home/justin/.hermes/hermes-agent`
- Branch: `main`
- Snapshot base commit: `2e6d1c686b docs: record Hermes upstream and browser cutover`
- Remote: `git@github.com:NousResearch/hermes-agent.git`
- Working tree: `clean`
- Recent commits:
  - `2e6d1c686b docs: record Hermes upstream and browser cutover`
  - `1a8188bbfc fix(browser): bound real-profile auth backup waits`
  - `7acd92d20f chore(local): baseline live Hermes runtime fixes`
  - `c32333dfae feat(memory): harden Hindsight retention and recall`
  - `2b26aa6dd8 docs: record Hermes memory bypass state`
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
  - `apps/desktop` `check`: `npm run check:lint && npm run test:ui && npm run test:desktop:platforms && npm run test:desktop:all && npm run check:test:plugins`
  - `apps/desktop` `check:lint`: `npm run typecheck && npm run lint`
  - `apps/desktop` `check:test:desktop:all`: `npm run test:desktop:all`
  - `apps/desktop` `check:test:desktop:platforms`: `npm run test:desktop:platforms`
  - `apps/desktop` `check:test:plugins`: `node --test src/plugins/*/tests/*.test.mjs`
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
<!-- REPO-STATUS:END -->

## Direction

Hermes is the live local agent gateway on `justinsdesktop`. Local `main` tracks
official `NousResearch/hermes-agent` upstream and carries a small reviewed patch
stack; `fork` is the pushable backup for those patches. Real-profile browsing is
consent-enabled for the default and Tyler profiles, and Firecrawl is the explicit
web-extraction backend for both.

## Recent Changes

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

## Verification

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
  `hermes-gateway-tyler.service` are active/running with `NRestarts=0` on the
  reconciled editable checkout.
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

## Next Work

- Official upstream advanced by 88 commits during the runtime repair. Reconcile
  the six carried commits onto current `origin/main` separately; none of those
  88 commits changes the SQLite/runtime repair path.
- Retain the parked vulnerable venv and the two verified state snapshots until
  the fixed runtime has completed the desired soak window. They are rollback
  assets, not active code.
- The pre-update incidental `package-lock.json` delta is preserved in stash
  `d2e1baab560ae481088b9abc4fa77f12aa545aba`; the old untracked generated
  `build/` directory remains excluded from source history.

## Blockers

- None for real-profile browsing, Firecrawl, or the Hermes upstream cutover.

## Constraints And Gotchas

- Missing `X-Hermes-Memory` means memory enabled. Unknown values fail with HTTP
  400, and the bypass header still requires normal API authentication.
- `browser.real_profile_autoclose` is intentionally false. The snapshot path may
  copy committed auth data from an open Chrome on POSIX, but Hermes never closes
  the user's browser or drives the live profile directly.
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
- Aivex Portal is retired. Keep technical continuity here, never in Portal.
