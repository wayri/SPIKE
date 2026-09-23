# Marble CLI qualification plan (SPIKE 0.2.10)

**Recorded:** 2026-09-06.  This is a bounded CLI compatibility and workflow
audit.  It is not a Berkeley Lab Marble qualification, PI/SI/thermal signoff,
or a statement about physical-board temperatures, power integrity, timing, or
EMC compliance.

## Pinned public source and local provenance

The test input is the official [BerkeleyLab/Marble][] hardware repository.  The
repository describes Marble as a dual-FMC FPGA carrier board and states that
the design documentation is licensed under **CERN OHL v1.2**.  It also directs
users to tagged releases for fabrication artifacts.  This audit therefore uses
the latest public annotated release visible on 2026-09-06, not a moving branch:

| Item | Value |
| --- | --- |
| Repository | `https://github.com/BerkeleyLab/Marble.git` |
| Ref requested | `v1.4.4` |
| Tag object | `6a632fd49997dcf77c1cc4288036044060cee03f` |
| Checked-out commit | `a426777d92c0f22a546d4740b419a3937e0c1f90` |
| Source board | `build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb` |
| Board SHA-256 | `3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512` |
| Source status | clean shallow clone, detached at the commit above |

The downloaded source is deliberately under `build/marble-qualification/` and
is not installer input.  The upstream checkout has no top-level `LICENSE`
file; the applicable source statement is retained in its `README.md`.  Preserve
that README and the upstream revision if these artifacts are redistributed.
No fabrication package, BOM purchase data, private board data, firmware, or
external solver was downloaded or executed.

[BerkeleyLab/Marble]: https://github.com/BerkeleyLab/Marble

## Evidence actually executed

Commands below used `.venv\\Scripts\\python.exe -m python.spike_cli` and the
installed CLI reported `SPIKE CLI 0.2.10`.

| Check | Result |
| --- | --- |
| `inspect Marble.kicad_pcb` | Completed: 30 layers, 1,374 nets, 37,380 tracks, 3,664 vias, 5,272 pads, 124 zones, 997 components, 29 stackup layers. |
| `validate Marble.kicad_pcb` | `valid: true`; warnings: 22 recoverable importer object diagnostics and 1 ambiguous component reference.  This is an import admission result, not geometry equivalence. |
| `extract-net ... --net +1V0` | Completed; `build/marble-qualification/net-1v0.geometry.json` is 1,535,827 bytes.  It includes F.Cu/In2.Cu/In4.Cu/In5.Cu/In6.Cu/In7.Cu/B.Cu geometry. |
| `setup-dc` | Completed and wrote a reproducible 80 MB DesignIR-embedded request.  Uses provisional F.Cu coordinates selected only from extracted geometry; they are not reviewed regulator/load terminals. |
| `setup-ac` | Completed and wrote a reproducible 80 MB request with the same provisional endpoints. |
| `thermal-estimate` | Completed on the synthetic one-node 8 W, 12.5 C/W, 20 J/C RC scenario.  Output is `approximate`; it returns 125 C solely by `T=Tambient+P*theta`.  It is CLI/API coverage, **not a Marble temperature estimate**. |
| `si-workflow` | Completed on a 33-point, 0--1 GHz user-defined uniform RLGC smoke network.  Result says `experimental`, `production_qualified: false`, and `compliance_status: not_evaluated`.  It has no Marble geometry. |
| DC preflight attempt | A 2 mm / 2,000-zone-cell / 500-conductor / 2 GB request began CPU-intensive preflight but produced no result file or admission diagnostic after 120 s.  The named test processes were terminated; no solve was started.  A duplicate observation process was also stopped early.  Treat this as an unresolved scale/performance blocker, not a failed physics calculation. |

Artifacts are all below `build/marble-qualification/`:

```
marble-inspect.json                 marble-validate.json
marble-nets.json                    net-1v0.geometry.json
marble-1v0-dc.request.json          marble-1v0-ac.request.json
smoke-thermal-scenario.json         smoke-thermal-result.json
smoke-si-workflow-request.json      smoke-si-workflow-result.json
capabilities.json                   solvers.json
capability-ledger.json
```

## Runnable paths and their limits

The CLI exposes runnable `analyze-dc`, `analyze-ac`, `analyze-transient`,
`thermal-estimate`, `si-geometry-channel`, and `si-workflow` commands.  Being
runnable is not equivalent to suitability for this board.

| Domain | Useful next command | Honest boundary |
| --- | --- | --- |
| DC PI | `preflight` then `run` on an endpoint-reviewed, net-isolated DC request | Sparse copper network is available but approximate.  Zone conclusions require mesh convergence; current terminal coordinates are not attribution evidence. |
| AC/PDN | `preflight` then `run` on an aggressively isolated power-path request | Quasi-static PEEC R/L and optional single-reference C/G are experimental.  Missing proximity effect, via/antipad C, general multiconductor electrostatics, radiation, and measured correlation. |
| Transient PI | `setup-transient` then `preflight` with a small net and explicit time/memory caps | Experimental R/L plus optional single-reference C; no dielectric loss/dispersion, via C, nonlinear devices, full-wave propagation, or regulator control loop. |
| SI | `si-geometry-channel` only after isolating one straight trace (or pair) over one verified reference plane; `si-workflow` for explicit RLGC/Touchstone | No arbitrary-board SI extraction, BGA/package transition extraction, connector/via/bend modeling, AMI/nonlinear IBIS, or protocol compliance claim. |
| Thermal | `thermal-estimate` only with reviewed per-source power, theta and capacitance; use case preparation separately for CFD | Compact independent RC only; it does not solve spreading, coupling, airflow, radiation, enclosure, or board temperatures. |

`capabilities.json`, `solvers.json`, and `capability-ledger.json` are retained
with this run as the machine-readable source for the above states.  The
`spike.peec_2_5d` and `spike.peec_rl_transient` catalog entries are explicitly
experimental/approximate.  The supplied `spike.mom_surface` and
`spike.fullwave_3d` entries are unavailable/unsupported.

## Resource and safety budget for a follow-up run

Do not use the full Marble board as an unconstrained PEEC or transient mesh.
First produce a reviewed endpoint map from schematic/BOM/layout ownership and
isolate a single rail segment.  The exact numbers below are conservative
operational controls, not demonstrated capacity.

| Stage | Budget / stop condition |
| --- | --- |
| Import/validate/extract | 120 s per command; retain diagnostics and hash. |
| DC/AC preflight | One job only; 120 s wall-clock.  Start at 2 mm mesh, 2 mm zone cell, 2,000 zone cells, 500 conductors, and 2 GB solver allowance.  Stop on any no-result timeout or unresolved importer diagnostic. |
| DC convergence | Only after preflight passes.  Compare at least coarse/medium/fine isolated-net meshes; stop if each run exceeds 120 s or if endpoint assignment changes. |
| AC | 11 frequency points from 1 kHz to 1 MHz first.  Increase bandwidth/points only after a bounded preflight and convergence record. |
| Transient | One isolated rail; <= 1 ms stop time, explicit <= 120 s solver time, 512 MB--2 GB memory budget, <= 500 branches, bounded output frames. |
| SI uniform-channel | <= 33 frequency points and no board geometry until the strict straight-path/reference-plane gates pass. |
| Thermal RC | One source only, with values from a reviewed measurement or datasheet.  Do not invent a full-board theta value. |

## Exact next commands

Use the pinned board and inspect output to select real, reviewed endpoints.  The
coordinates below are intentionally placeholders from the successful `+1V0`
geometry extraction and must be replaced before any result is interpreted.

```powershell
$board = 'build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb'
$py = '.venv/Scripts/python.exe'

& $py -m python.spike_cli --output build/marble-qualification/recheck.json validate $board
& $py -m python.spike_cli --output build/marble-qualification/one-rail.json extract-net $board --net '+1V0'

# Create only; does not solve. Replace endpoints with schematic-reviewed pads.
& $py -m python.spike_cli --output build/marble-qualification/one-rail-dc.json setup-dc $board `
  --net '+1V0' --source '228.27,142.0,F.Cu,1.0' --load '234.27,146.0,F.Cu,0.5' `
  --return-net GND --return-source '228.27,142.0,F.Cu,0' --return-load '234.27,146.0,F.Cu,0.5' `
  --mesh-size-mm 2 --zone-cell-mm 2 --max-zone-cells 2000 --max-conductors 500 --memory-limit-gb 2

# Run this only under the 120 s preflight wall-clock guard described above.
& $py -m python.spike_cli --output build/marble-qualification/one-rail-dc-preflight.json preflight build/marble-qualification/one-rail-dc.json
```

Before SI work, use a purpose-built short, straight channel fixture or provide
measured/imported Touchstone.  Before thermal work, obtain source power and
thermal-resistance evidence.  Before calling any result a Marble qualification,
resolve importer diagnostics, establish endpoint/return-path ownership, record
mesh convergence, and correlate against measurements or an independently
validated solver.
