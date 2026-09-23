# Marble feature checkpoint (2026-09-06)

This checkpoint records a bounded repeat of the Marble CLI evidence in
`docs/MARBLE_CLI_QUALIFICATION_PLAN.md`.  It is not a Berkeley Lab Marble
qualification, fabrication signoff, or statement about the board's PI, SI,
thermal, timing, EMC, or measured performance.

## Scope and inputs

The input remains the pinned `BerkeleyLab/Marble` `v1.4.4` checkout described
in the plan:

```
build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb
```

The CLI exercised here was `SPIKE CLI 0.2.10`.  Only import/validation and the
small built-in solver corpus were re-run.  No full-board DC, AC, transient,
SI, thermal, or external-solver execution was started.

## Results

| Feature | Checkpoint status | Evidence / boundary |
| --- | --- | --- |
| KiCad import and inspection | **Passed** | Existing inspect result reports 30 layers, 1,374 nets, 37,380 tracks, 3,664 vias, 5,272 pads, 124 zones, and 997 components. Import retains 22 recoverable object diagnostics. |
| Marble validation admission | **Passed with warnings** | Refreshed `validate` returned `valid: true`, with the 22 importer diagnostics and one ambiguous component reference. This is not geometry-completeness evidence. |
| `+1V0` net extraction | **Passed** (existing evidence) | `net-1v0.geometry.json` exists (1,535,827 bytes); it is geometry export, not reviewed terminal attribution. |
| DC request construction | **Passed** (existing evidence) | `setup-dc` request exists. Its endpoints are explicitly provisional in the qualification plan. |
| DC preflight | **Failed / blocked** | `marble-1v0-dc.preflight.json` is `blocked`, `can_solve: false`. It reports connection-evidence input above 64 MiB, a 500-branch limit breach, and a truncated mesh preview. No DC solve result exists. |
| DC result and mesh convergence | **Not run** | Blocked by the preflight result; endpoint ownership and convergence evidence are also absent. |
| AC request construction | **Passed** (existing evidence) | `setup-ac` request exists, using the same provisional endpoints. |
| AC preflight and solve | **Not run** | No bounded AC preflight/solve result was found or started. The capability ledger marks AC/RLCG experimental. |
| Geometry-derived transient | **Not run** | No Marble transient request or result was found or started. The capability ledger marks it experimental. |
| SI geometry channel on Marble | **Not run** | No isolated straight channel with a verified reference plane was supplied. The available geometry channel is bounded to straight, uniform reference cases; arbitrary-board quasi-TEM extraction is unsupported. |
| SI workflow smoke fixture | **Passed** (non-Marble evidence) | Existing 33-point explicit-RLGC smoke workflow completed, but contains no Marble geometry and is experimental/non-qualified. |
| Compact thermal RC smoke fixture | **Passed** (non-Marble evidence) | Existing synthetic one-node thermal RC run completed. It is not a Marble temperature result. |
| Marble solid thermal / airflow | **Unsupported / not run** | Reviewed source powers, thermal contacts, enclosure, and airflow are absent. The ledger lists solid steady thermal as implementation pending and conjugate heat transfer as unsupported. |
| Electrothermal or EM-thermal coupling | **Unsupported / not run** | Ledger state is unsupported; no reviewed board inputs or coupled case exists. |
| Built-in solver benchmark corpus | **Passed** | Fresh `benchmark` report: 15/15 passed, 0 failed, 0 skipped. These are analytical/fixture checks, not a Marble-board benchmark. |

## Commands executed for this checkpoint

```powershell
$board = 'build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb'
$py = '.venv/Scripts/python.exe'

& $py -m python.spike_cli --version
& $py -m python.spike_cli --output build/marble-qualification/marble-validate-checkpoint-20260906.json --quiet validate $board
& $py -m python.spike_cli --output build/marble-qualification/solver-benchmark-checkpoint-20260906.json --quiet benchmark
```

The validation and benchmark commands completed within the 60-second
per-command limit.  The generated reports are retained under
`build/marble-qualification/`; that directory is evidence storage and is not
an installer input.

## Required evidence before board-result interpretation

Resolve or disposition the importer diagnostics, identify schematic-reviewed
source/load/return terminals, isolate one rail segment, and pass a bounded
preflight.  Only then should DC, AC, or transient execution begin, with a
recorded coarse/medium/fine mesh-convergence series.  SI requires a verified
straight path and reference plane (or reviewed Touchstone); thermal requires
measured/datasheet power and thermal-resistance data.  Measured or
independently validated-solver correlation remains necessary for any physical
board claim.
