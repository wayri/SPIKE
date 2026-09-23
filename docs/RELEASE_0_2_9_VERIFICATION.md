# SPIKE desktop 0.2.9: integrated engineering preview

**REJECTED after native UI acceptance.** The absolute Windows snapshot path was
interpreted as a URL and opened a directory listing. Matching installed hashes
and 21/21 worker checks did not establish frontend usability. The failed archive
is retained with `REJECTED.md`; 0.2.10 must replace this candidate. The relative
path fix compiled successfully, but no corrected 0.2.9 was installed before the
user stopped Computer Use. Historical qualification notes below are not approval.

Date: 2026-09-06. Release and installation checks are in progress. This document
will record the exact final candidate; it is not itself an acceptance certificate.

## Scope and capability boundaries

| Workflow | Implemented use | Still not established |
|---|---|---|
| PI | Board DC resistive-network/FV analysis; experimental RLCG/PDN/transient paths; native MNA, PEEC/MNA and structured owned-SPIKES circuit workflows | Complete measured/independent board correlation and production signoff |
| SI | Supported geometry-to-RLGC channels and imported S-parameter networks; loaded response, S-parameters, TDR/TDT and bounded eye calculations; protocol workspaces | Arbitrary via/package/connector field extraction, general nonlinear driver behavior, calibrated BER/jitter and protocol compliance |
| Thermal desktop | Compact screening and externally prepared/executed OpenFOAM cases, with imported fields and capability checks | Full PCB-solid/contact/airflow/CHT/radiation/fan/potting/electro-thermal signoff |
| Thermal reference tools | Structured-grid conduction/contact/radiation, convergence/energy checks, steady resistor-network electro-thermal iteration and bounded prescribed-current diode reference | General CAD-to-volume translation and full desktop integration; general semiconductor transient coupling |
| MCAD export | Explicit named STEP/FCStd/BREP solids, groups, material metadata and digest-checked artifact saving | Automatic complete PCB copper/drill/component/flex geometry and solver-qualified material semantics |

The SI numerical workflows are real but bounded. Historical capability-ledger
entries alone must not be read as proof that all S-parameter/TDR/eye functions
are absent. Conversely, an implemented plot or protocol workspace is not proof
of protocol compliance or arbitrary-board extraction.

## Integrated changes

- PI sources/sinks, batch and return terminals, and SI endpoints use tables.
- Owned-SPIKES structured-workspace execution is selectable. Its worker request
  now requires `spice.execute` and is serialized as a heavy operation in both
  renderer and native host; validation remains a separate lightweight operation.
- Includes current MCAD export, ODB import work and existing layer/model repairs.
  Public corpus failures remain: 20/22 normalized imports, 15 exact save/reopen
  passes, with ODB errors and large-package limits explicitly unresolved.

## Evidence under collection

- Source identities: `build/desktop-0.2.9-packaged-source-snapshot.json` (921
  files after help regeneration). Later unwired `projectSnapshotState.ts`,
  `project_state_artifacts.py` and `project_visual_artifacts.py` belong to the
  parallel 0.2.10 persistence follow-up, not this frozen candidate.
- Full Python run: `build/qualification-desktop-029-current.log`.
- Frontend/type run: `build/frontend-qualification-029-current.log`.
- Builder: `build/desktop-0.2.9-build-final.log`. Initial sandbox Vite access
  failure is retained separately in `build/desktop-0.2.9-build.log`.
- Analytical/numerical benchmark reports are under `build/capability-benchmarks/`;
  they explicitly separate mathematical component checks from measured validation.

Completed gates: 1,426 Python tests (zero failures/errors, one skip); all 46
frontend suites plus TypeScript after regenerating the stale help index; 31
native-host tests; 180 packaged Python modules match source. Packaged runtime
parity passes 8/8 and packaged solver benchmarks 15/15, with Arrow, owned-engine
interactive replay and extension execution probes passing.

The benchmark run `run-20260905T191508.514990Z/report.json` passes 111 numerical
tests, 46 adapter/evidence tests, five repeated analytical probes and 95 native
mathematical verification executables. Its source/runner/native hashes remain
stable. These are component results from the existing native build, not fresh
distributed builds or independent/measured signoff.

Parallel visualization and release builders collided in shared bundler outputs.
Their intermediate installers are not the final candidate. After the other
builder completed and the diagnostic competing retry was stopped, this task
took sole ownership and used `tauri bundle` against a fixed tested desktop and
worker. Final packaging log: `build/desktop-0.2.9-single-owner-bundle.log`.

The user requested full capability and local installation. The candidate may be
installed as an engineering preview when build/regression checks pass, but the
remaining scientific and cross-platform acceptance work is not marked complete.
