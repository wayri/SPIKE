# PI/SI capability audit — 0.2.10 frozen-worker scope

**Date:** 2026-09-06. **Scope:** read-only audit of the 0.2.10 source
contracts, CLI, documented packaged-worker boundary, and focused Python
regressions. No source, native binary, frozen worker, or installer was changed
or rebuilt. This is not a production-qualification statement.

## Bottom line

The practical PI entry point is an **approximate DC copper solve**. Native
quasi-static AC/PEEC and PEEC transient paths are executable, but remain
**experimental**. PDN review, explicit-port capacitor screening, and bounded
capacitor-bank search execute, but their placement result is only as valid as
the supplied network and is explicitly not physical-placement signoff.

SI is useful for imported Touchstone networks and a deliberately bounded
uniform straight one-/two-line channel. It does **not** support arbitrary-board
SI extraction or a production BGA/package workflow. There is no demonstrated
5,000-ball BGA analysis scale. The release ledger has no release-ready PI or SI
workflow, and the documented PI release gate is fail-closed.

| Requested capability | Status | What is actually runnable | Evidence and material boundary |
| --- | --- | --- | --- |
| PI DC copper drop/current/density | **Working, approximate** | `analyze-dc`/`run` use the sparse copper network for tracks, vias, pads and polygon zones; results include voltage, drop, branch current, density and loss. | `python/spike_core/capabilities.py` reports `dc: available`, `model_status: approximate`; `docs/SOLVER_STATUS.md` requires zone mesh convergence. Ledger: `pi.dc_conduction`, `implemented_approximate`. No measured-board or signoff claim. |
| PI AC to a few GHz | **Experimental** | `analyze-ac`/`run` expose frequency-dependent R, partial L, optional single-reference C/G and complex Z(f). The request accepts any frequency range, but the solver itself reports/checks quasi-static validity. | `docs/CLI_WORKFLOW.md` shows a 1 kHz–30 MHz example; `capabilities.py` calls broadband HF experimental. Missing: proximity, via/antipad C, arbitrary multiconductor electrostatics, full-wave radiation and measured correlation. Therefore “few GHz” is an input range, not demonstrated board-accuracy bandwidth. |
| Geometry PI transient | **Experimental** | `analyze-transient`/`run` perform fixed-step backward-Euler PEEC R/L plus optional single-reference C with constant/step/pulse/PWL excitations. | `docs/SOLVER_STATUS.md`; ledger `pi.geometry_transient`. No nonlinear devices, adaptive timestep, via C, dielectric loss/dispersion, radiation, transmission-line propagation or closed-loop source model. |
| Decap review/optimization and placement | **Experimental screening** | `pdn-review` detects target violations/resonance extrema and screens lumped candidates; `pdn-optimize` searches declared ports/library within finite bounds. PEEC can produce bounded candidate multiport data. | `docs/PDN_SCREENING.md` documents a default 16/hard 64 PEEC candidate-port limit and an ideal common reference. `docs/PDN_OPTIMIZATION.md` says it neither infers placement nor mounting parasitics; 4,096 schema limits are input bounds, not a scalability result. No regulator-loop, vendor-model, package/mounting, plane-spreading or hardware-ranking validation. |
| Plane resonance / anti-resonance | **Partial, screening only** | PDN review reports extrema in a *supplied* driving-point impedance sweep. | It is not a plane-mode/full-wave resonance solver. `docs/validation/MODULAR_BUS_NIB_ANALYSIS.md` explicitly excludes resonance/anti-resonance conclusions where the source model lacks full PDN content; AC PEEC omits the capacitance/return physics required for a general plane-resonance claim. |
| Tabular PI inputs; adjustable column widths | **Working inputs; resizing missing** | Active Tauri `TerminalTable` provides editable name, coordinates, connection, source/load value, contact/package resistance, actions and lazy details. `App.tsx` uses it for DC, AC, transient and batch source/load rows, plus return paths. | `app/src/TerminalTable.tsx` and `.css`; `app/scripts/test-terminal-table.mjs` passes rendering, lazy 100-row details, edits, removal, return, transient and batch wiring. Its fixed `table-layout`, fixed minimum width and only two CSS column widths do not provide user resize controls or persistence. The frozen wxPython `SetColSize` is not supported-runtime evidence. |
| SI, arbitrary board geometry | **Missing** | `si-geometry-channel` supports one straight path or two parallel coextensive paths over one proven reference polygon; `si-workflow` runs loaded imported/RLGC networks. | `capabilities.py` explicitly excludes bends, vias, launches, connectors, general PCB coupling/extraction and compliance. Protocol suites configure inputs only. |
| SI BGA/package and “5,000 BGA” scale (balls or parts) | **Missing** | No native BGA/package extraction workflow or scale fixture was found. | The only BGA hit in scope is IPC-2581 pad/via import coverage (`tests/python/test_ipc2581_pad_via_import.py`), not PI/SI extraction. Whether “5,000 BGA” means 5,000 balls or 5,000 BGA components/parts, neither has an extraction, memory/time, convergence or accuracy benchmark. The 5,000 limit in `design_ir_v2.py` is for AssemblyIR contacts/bonds, not balls, parts or solver capacity. PEEC admission is RAM-derived; the recorded real-board example is 1,207 filaments, not either 5,000-BGA case (`docs/PI_RELEASE_QUALIFICATION.md`). |

## Exact CLI entry points

Run from the repository root. `--output` writes the resulting JSON contract.

```powershell
# Inspect declared capability and native-release ownership/status.
python -m python.spike_core.cli --output capabilities.json capabilities
python -m python.spike_core.cli --output ledger.json capability-ledger

# Design import, DC, AC and transient PI workflow.
python -m python.spike_core.cli --output design.json import board.kicad_pcb
python -m python.spike_core.cli --output dc-request.json setup-dc design.json --net VCC --source "x,y,F.Cu,5" --load "x,y,F.Cu,1"
python -m python.spike_core.cli preflight dc-request.json
python -m python.spike_core.cli --output dc-result.json run dc-request.json
python -m python.spike_core.cli --output ac-request.json setup-ac design.json --net VCC --source "x,y,F.Cu,SRC" --load "x,y,F.Cu,LOAD" --start-hz 1e3 --stop-hz 1e9 --points 201
python -m python.spike_core.cli --output ac-result.json run ac-request.json
python -m python.spike_core.cli --output transient-request.json setup-transient design.json --net VCC --source "x,y,F.Cu,SRC" --load "x,y,F.Cu,LOAD"
python -m python.spike_core.cli --output transient-result.json run transient-request.json

# PDN review/search: inputs must declare the network, ports, library and assumptions.
python -m python.spike_core.cli --output pdn-review.json pdn-review ac-result.json --target-ohm 0.05 --net VCC --candidate-file candidates.json
python -m python.spike_core.cli --output pdn-opt.json pdn-optimize ac-result.json --target-ohm 0.05 --net VCC --library capacitor-library.json

# Experimental SI paths.
python -m python.spike_core.cli --output si-channel.json si-geometry-channel design.json uniform-channel-request.json
python -m python.spike_core.cli --output si-study.json si-workflow si-workflow-request.json --touchstone-output edited-channel.s2p
```

`pi-release-qualification` is a negative release check, not a promotion path:

```powershell
python -m python.spike_core.cli --output build/pi-release-qualification.json pi-release-qualification --runtime-report build/release-runtime-qualification-current.json --benchmark-report build/native-benchmark-current.json
```

`docs/PI_RELEASE_QUALIFICATION.md` records its current status as `blocked`;
all six required PI workflows remain unpromoted. The CLI has no
`solver-suite-deployability` command; that report is a Python module/test
surface, not a released command.

## Evidence executed for this audit

The following focused source tests were run successfully on 2026-09-06:

```powershell
python -m unittest tests.python.test_capability_ledger tests.python.test_solver_suite_deployability tests.python.test_pdn tests.python.test_si_workflow
```

Result: **40 tests passed**. They cover ledger fail-closed state, PDN analytic
loading/ranking contracts, and loaded SI network calculations. They do not
validate arbitrary PCB accuracy, BGA/package models, 5,000-ball capacity,
column resizing, or hardware correlation.

The active terminal-table check was also run successfully:

```powershell
node app/scripts/test-terminal-table.mjs
```

It confirms editable DC/AC/transient/batch and return-path table wiring, but
does not test column resizing or saved width state.

The native CMake test registrations exist for `test_peec`,
`test_spikes_core`, `test_spikes_transient`, and transient C API/session tests
(`CMakeLists.txt`, test registrations around lines 239–326). They were **not
built or executed** in this frozen-0.2.10 audit. Existing source/package
integrity checks in `docs/NATIVE_DESKTOP_RUNTIME.md` establish loading and
parity of a packaged native PEEC plugin; they explicitly do not qualify
numerical accuracy for arbitrary PCBs.

## Workflow gaps that matter before using this as a general PI/SI tool

1. Independently correlate AC/PDN multiport extraction—including return paths,
   plane spreading, via/antipad and package/mount models—then validate decap
   ranking on physical boards.
2. Add a validated, arbitrary-geometry SI extraction and package/BGA transition
   path before treating protocol setup, Touchstone inspection, or uniform-line
   results as board SI signoff.
3. Establish resource and accuracy benchmarks for representative BGA sizes;
   specifically include a 5,000-ball fixture, memory/time admission results,
   and convergence/correlation criteria.
4. Implement and test supported-client column resizing/persistence if editable
   tabular widths are a product requirement.

## Proposed minimal terminal-column resize design (not implemented)

Keep `TerminalTable` reusable and make width state an optional controlled
property, for example `columnWidths?: Record<TerminalColumnId, number>` with
`onColumnWidthsChange`. Render a small separator button in each resizable
header, with `role="separator"`, an accessible column name, `aria-valuemin`,
`aria-valuemax` and `aria-valuenow`. Pointer drag changes only that column's
CSS custom property; clamp widths to readable minima and preserve the existing
horizontal scroll behavior. Keyboard support should focus the separator:
Left/Right changes width by 8 px, Shift+Left/Right by 32 px, Home/End selects
the allowed minimum/maximum, and Escape restores the pre-drag value.

Persist width records in the existing project/UI state under a versioned,
table-specific key (for example `terminalTableWidths.v1`), validate unknown
keys and out-of-range values on load, and retain defaults when absent. Tests
should cover pointer and keyboard changes, clamps, Escape reset, ARIA values,
DC/AC/transient/batch/return shared rendering, and project save/reopen.
No production source change is included in this audit.
