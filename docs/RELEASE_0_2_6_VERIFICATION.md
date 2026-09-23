# SPIKE 0.2.6 stability release verification

Date: 2026-09-05. Channel: unsigned Windows engineering preview.
This release does not promote numerical physics, compliance or production gates.

## Scope

GLB/VRML dispatch for verified Blob URLs; raw-board import state isolation;
Windows source-byte preservation for package save/Save As; physical copper
wildcard resolution; readable warning cards; linear component-pick indexing;
legacy hidden-layer visual export. Existing concurrent topology work is retained.

The supported worker is CPython 3.12.9, not the system CPython 3.11. Its matched
PEEC extension and current owned SPIKES DLL are bundled. The stale hybrid DLL
was backed up as `build-spikes-hybrid/spikes_c_api.dll.pre-runtime-repair-20260905-1804.bak`.
The replacement DLL SHA-256 is
`e0bf3047410bb7d6e664583d0238828777520ec62090b0468ee6428dbca809f5`.

## Evidence collected before final packaging

- Full CPython 3.12 discovery: **1,349 run, no failures/errors, one skip**, in
  224.027 seconds; `build/qualification-desktop-026-frozen.log`, exit 0.
  This supersedes intermediate runs taken while other tasks were editing.
- Native ABI/geometry: 31/31 pass, including electro-thermal circuit case.
- Supervisor lifecycle/resource checks: 6/6 pass. Venv process-launcher tests
  now invoke the base interpreter directly inside the one-process Job Object;
  the production containment policy is unchanged.
- Core and hidden-layer export tests: 41/41 pass.
- Rust desktop: 29/29 pass with the configured preview public key. The test
  checks the actual build-pinned key; runtime signature verification is unchanged.
- Analytical worker benchmark: 15/15 and runtime parity: 8/8 in the worker build.
- TypeScript/Vite and architecture checks pass; large frontend chunks remain.
- All 42 frontend `test:*` suites pass against the 886-file source snapshot
  `build/desktop-0.2.6-source-snapshot.json`. Help tests cover search, links,
  safe Markdown, 87 CLI pages, 91 diagnostics and 1,151 control locations.
- The final assembly-source regression binds imported native boards to their
  exact `package:sources/<SHA-256>` artifact and aborts atomically on source
  identity mismatch. Combined assembly/package checks: 43/43; package
  signature, source-URI and digest validation were not weakened.
- Downloaded OLIMEX OLED and Raspberry Pi RP2040 fixtures parse and round-trip
  through package save/Save As/reopen. Corpus provenance is recorded in
  [the stabilization plan](STABILIZATION_RELEASE_PLAN_20260905.md).
- Real KiCad 10 export of OLIMEX now emits all 20 drawable layers including
  legacy `(31 B.Cu signal hide)`, up from 19 before the fix. Both board/component
  GLB containers are valid. Ten missing legacy component-library references are
  explicitly reported; the near-empty component GLB is not model completeness.
- The RP2040 board exports 20 layers and a 5,355,020-byte board GLB. A restricted
  test initially returned 30 unresolved embedded models: KiCad's official cache
  under `%LOCALAPPDATA%/KiCad/10.0/embed` could not be written. The identical
  components-only CLI command with normal per-user permissions exits 0 with no
  missing references and a 2,014,712-byte component GLB. The board's STEP assets
  are valid; no custom embedded decoder or substitute geometry was introduced.

## Installation evidence

Both final installers were built at 2026-09-05T13:33:43Z. Source identities
remained unchanged after worker and installer builds (886 tracked inputs).

| Artifact | SHA-256 |
|---|---|
| `SPIKE_0.2.6_x64-setup.exe` | `d4ca9c925d06fb6efcf39ef06d222ba325a547c4ba171221771ddbe671598d56` |
| `SPIKE_0.2.6_x64_en-US.msi` | `ff6ed411a201b2456f38638507f456bfb8638e2c94629ec84d1420bfcda77b08` |
| Built `spike-desktop.exe` | `bd2667ca1f88034b45f96ebbe0e612c14f61305d905e24ecc79b9a58682aa17a` |
| Built `spike-worker.exe` | `099b1369b7ce74e1b4443ecb458915a17200e896f17627b7b508daf5dab7a6cb` |

Artifacts and manifest are in `artifacts/windows/installer/`. Both packages are
also preserved with their manifests, runtime report and source identities in
`artifacts/windows/releases/0.2.6-stability-20260905/` so concurrent builds cannot
replace this verified candidate. Both packages are
`NotSigned`; production qualification remains false. Worker runtime parity8/8
and benchmark15/15 pass, with runtime digest
`b6455e0a7914a0fe4d8be4d60a46303fd6ffa7a87464ab08b27510d1376e0617`.

**Not installed yet:** the existing SPIKE process (PID31104 at the final check)
is running from `C:/Users/yawar/AppData/Local/Programs/SPIKE/spike-desktop.exe`.
The user was asked to save and close it; no forced termination or overwrite of
an in-use installation was performed. Exact installed-image and native UI
acceptance remain pending until the upgrade can safely run.
The existing 0.2.5 installation is preserved at
`artifacts/windows/rollback-pre-0.2.6/`; user settings/projects are not removed.

## Remaining qualification

A later live-tree fix in `assembly_exchange.py` binds native board assets inside
`.spikeassembly` archives to canonical source URIs. That fix and its new
regression are not in this archived candidate. Embedded native-board exchange
import must not be claimed working on the basis of this release's test totals.

Representative 10/32-layer and high-density interactive performance, complete
custom-pad/thin-net solving, every viewport/layer combination, clean-machine
Windows upgrade/uninstall and Linux qualification remain separate acceptance
work. Broader editor/dashboard/report and thermal/SI/PI signoff requirements in
the stabilization plan are not marked complete by this maintenance release.
