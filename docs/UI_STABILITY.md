# UI stability regression runner

The frontend stability gate runs every `test:*` command declared in
`app/package.json`, except the runner itself. From `app`, run:

```powershell
npm run test:ui-stability
```

Suites run sequentially to keep CPU and memory demand bounded. Each suite has a
five-minute default timeout. Set `SPIKE_UI_TEST_TIMEOUT_MS` or pass
`--timeout-ms=<milliseconds>` after `--` when a slower supported environment
needs a larger bound:

```powershell
npm run test:ui-stability -- --timeout-ms=600000
```

The runner checkpoints `.local/ui-stability-tests.json` after every suite and
returns a nonzero exit code if any executed suite fails or times out. The report
records the declared package command, duration, exit code, signal, timeout
state, bounded output, and extracted failure lines. Use `--report=<path>` to
choose another repository-relative report path. Use `--dry-run` to inspect the
discovered suite list without executing it.

For runner development or focused diagnosis, repeat `--suite=<package-script>`
to select named suites. CI and release evidence use the unfiltered command.

Only identical complete package commands are deduplicated. The runner does not
split compound commands because their ordering and shell short-circuit behavior
are part of the declared suite. An underlying test file may therefore run more
than once when it is intentionally included by different compound suites.

## Coverage boundary

The runner exercises the checked-in Node static and behavioral regression
harnesses. Those suites cover parser, workspace, persistence, presentation,
viewport policy, interaction-model, report, and workflow contracts represented
in `app/scripts`.

A passing run does not establish native Tauri or WebView interaction behavior,
installed-package behavior, visual correctness at supported window sizes,
screen-reader behavior, solver physics, or numerical accuracy. Record native
desktop interaction and visual acceptance separately. Keep solver validation
and the Python, Rust, architecture, packaging, and release gates separate from
this frontend runner.

## 0.3.10 audit evidence

The audit inventories 1,968 control sites, including 378 requiring runtime
context. This is an inventory, not a claim that each state has been clicked.
Live browser checks exercised all nine application menus and twelve workspace
tabs, search availability/Escape recovery, project-manager focus handling at a
900-pixel window, and 900/1440-pixel layout width. A retained ebrake1 board import,
B.Mask visibility independent of copper toggles, and seven camera commands were
also exercised. Browser preview cannot run desktop solver operations, and
camera command dispatch alone does not establish geometric orientation accuracy.

Native 0.3.9 reproduced the menu Escape failure. The reported lingering-close
issue led to the desktop lifecycle repair. The 0.3.10
close behavior has separate frontend save/cancel/draft regressions and native
worker lifecycle tests. Installed-package startup and real shutdown are required
Windows release gates. See [close recovery](DESKTOP_SHUTDOWN.md).

Final local gate: all 108 frontend suites passed in 116.9 seconds; the
production frontend build passed. Architecture and release-version checks passed,
seven changed Markdown files passed documentation checks, and 18 focused Python
release/installer/CLI tests passed. Native tests passed 42 cases with one existing
live GPU case ignored and the packaged-worker case excluded locally because its
payload was absent. Packaging CI must run that installed-payload gate.
