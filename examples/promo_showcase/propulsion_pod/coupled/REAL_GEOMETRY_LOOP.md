# Real-source geometry loop: headless integration

This is a separate workstream from the completed synthetic FEM/BEM reference
in README.md. It is not yet a completed real-hardware demonstration. Do not
reuse the older reference archive as evidence that blade CFD has converged.

The source pair is the pinned OpenMotor CIAG_2_28 125_25 STEP and ENOLA
Casalino +5 degree 300 mm propeller STL in `../real_hardware/`. Their original
licenses and notices remain attached. This composed pair has no common measured
test record. The VESC source board is electrical context; the compiled sampled
controller is an explicit demonstration controller, not the VESC firmware.

The current headless integration consists of:

- Native rotor/stator geometry, conforming quadratic magnetic fields, and a
  separately derived analytic annular Fourier operator. A rotationally repeated
  source-verified rotor mesh preserves the actual 14-fold mechanical symmetry.
  Phase flux, cogging and current torque follow from one quadratic coenergy.
- A scalar periodic coenergy table, with positive balanced inductance checks.
  It is a constitutive surrogate of retained field solves. Independent mesh,
  trace, Fourier and angular-interpolation checks remain necessary.
- Blade-resolved quasi-steady CFD anchors and an immutable PCHIP load table.
  Each load evaluation supplies shaft reaction and power consistently. Table
  interpolation is not a new CFD solve or a time-resolved fluid wake.
- The actual compiled C controller, implicit phase/shaft exchange and thermal
  resistance feedback. The eleven-node thermal network uses declared lumped
  parameters; it does not imply a resolved CHT or winding-loss qualification.

The magnetic straight-chord trace geometry and Fourier cutoff are explicit
approximations. Material substitutions and intended winding interpretation are
not manufacturer-qualified. CFD auxiliary-density continuation is numerical
initialization; only the final actual-air stage may supply an air-load anchor.
Algebraic residual, mesh/domain load change, recovered traction and energy
checks are separate evidence. No gate may be waived to make the loop run.

## Execute retained inputs

Once actual field/load tables and their independent convergence receipts exist,
run from the repository root:

```powershell
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/coupled/run_geometry_loop.py --magnetic-table <field-table.json> --cfd-table <load-table.json> --request <loop-request.json> --output <new-result.json>
```

The request contains exactly `initial_currents_a`, `initial_angle_rad`,
`initial_speed_rad_s`, `thermal`, `drive`, `shaft` and `transient`. Drive includes
the explicit three end-turn inductances. The runner retains hashes of all input
files, controller executable identity, time history and whole-loop energy ledger.
It rejects an existing output path and CFD extrapolation. Construction of input
objects verifies their numerical representation, not the truth of supplied
convergence claims. Numerical qualification and human release review remain
separate from a successful time integration.

For GUI packaging retain the exact magnetic/load tables, request, result,
convergence receipts, modified-geometry notices and source data. All embedded
KiCad inputs must also be present as adjacent native files and complete available
project/library companions via `colocate_kicad_sources.py`. GUI verification is
pending; no computer use is part of this headless workstream.

## Prepared native geometry project

`prepare_real_source_assets.py` and `build_real_source_project.py` were executed
headlessly. The retained project is
`output/promo-propulsion-pod-20261023/real_geometry/real-source-pod-assembly-pending-simulation.spike`.
Native reopening and exact adjacent KiCad byte checks passed. It includes the
actual-source motor display tessellation and all 35,744 original propeller
facets, with the original STEP/STL and licenses adjacent. The motor display
tessellation has 4,130,334 triangles at declared 0.5 mm visual deflection; this
large display asset is independent of the much smaller solver meshes.

The project explicitly retains `complete_loop=false` and `gui_verified=false`.
Its proposed common-axis propeller position is a declared scene placement, with
the mounting adapter unresolved. The VESC board is source context. Neither this
prepared geometry project nor the older synthetic benchmark is the completed
real motor/blade-CFD loop.

## Retain a completed run for later GUI verification

`package_geometry_loop.py` accepts the prepared native source project, an actual
completed `run_geometry_loop.py` result, its exact request/magnetic/CFD input
files, and retained evidence directories. It checks the executed input-file
hashes and canonical constitutive-table identities before creating a new native
project. It retains the original project, embeds the completed capture, copies
the evidence and source assets, and checks native reopening and exact adjacent
KiCad bytes. `PACKAGE_INVENTORY.json` records the retained file hashes.

Packaging also binds every retained field source to the scene's original motor
STEP, and `cfd_table.evidence.source_geometry_sha256` to the scene's original
propeller STL. All adjacent asset bytes must match the prepared manifest. A
result from another model cannot be attached to these visual assets as this pod.

The versioned `spike/geometry-propulsion-ui-study/v1` capture uses the existing
project study persistence slot `analysis.propulsion_pod_three_phase` for backward
compatibility; its contract dispatches to the separate geometry capture panel.
It does not pass through the synthetic motor/BEM result parser. The panel shows
accepted endpoint currents, angle, speed and thermal-network temperatures, and
separately labels preceding-interval discrete-gradient torque and midpoint CFD
table loads. Replay reads stored states. It does not start a new solver or
invent a spatial magnetic/thermal field from the scalar histories. Saving without
results preserves the explicit setup and removes the capture.

Capture admission rejects incomplete/nonfinite histories, missing source hashes,
mismatched solved setup, future contracts and physical qualification claims.
TypeScript compilation, capture-admission checks, project snapshot round trips,
button-standard and architecture guards passed headlessly. The package helper
has not been exercised with a completed real loop because the required actual-air
CFD load remains pending. Native runtime layout and visual verification remain
pending under the user's no-computer-use instruction.

`attach_geometry_snapshots.py` reconstructs actual P2/Fourier fields at selected
accepted endpoint currents/angles. It requires the table's exact retained domain
file SHA-256, native source/spec identity, stack depth and Fourier cutoff. It
retains a separate derivation receipt and original result-file hash. The saved
result panel shows these centroid-sampled display patches with one shared |B|
scale, and rejects fields associated with different currents, angles or source
geometry. Replay advances through saved spatial states when available. It does
not generate intermediate fields. These reconstruction and native packaging
commands await the actual completed real-source loop; parser fixtures are not
simulation evidence.

Before packaging, admit the actual enriched result with
`node app/scripts/check-geometry-pod-capture.mjs <actual-result.json>` from the
repository root. Thermal defaults expanded by the runner are retained as the
effective solved setup; the original request bytes and their executed hash are
also copied unchanged. Result admission does not establish physical accuracy.

`real_geometry_loop_request.json` declares a 48 V averaged-bridge scenario with
an already spinning restrained shaft, initial190 rad/s, target200 rad/s,40 ms
duration,10 us integration and20 us controller sampling. Its adjacent
`.assumptions.json` records the conditional source-derived winding resistance,
declared total inertia, omitted end-turn leakage inductance and illustrative
thermal parameters. It is an unexecuted request until actual tables exist;
controller demand6 A does not impose a physical protection clamp. A paired5 us
integration at unchanged20 us controller sampling is required for the intended
timestep comparison. A CFD table must cover every accepted trial speed; the
runner refuses extrapolation.

`compare_geometry_timesteps.py --coarse <10-us-result.json> --fine <5-us-result.json>
--output <new-comparison.json>` compares common accepted endpoints, preserving
the controller sampling period and all other effective inputs. It requires
identical magnetic, fluid, controller-source and orchestrator identities, and
retains both result-file hashes. It reports current, flux, speed, angle,
temperature, torque and cumulative energy changes. Two resolutions provide an
observed change, not a true-error bound or convergence order; no pass threshold
or physical qualification is inferred. Its three fixture tests passed; the
actual paired real-source executions remain pending.

The fine-grid request is prepared as `real_geometry_loop_request_5us.json`,
with its own request-byte-bound `.assumptions.json`. Its duration and20 us
controller sampling match the10 us request; neither file is execution evidence.

The prepared native package can include the exact table-bound motor reference
audit using `--reference-audit`, and the exact request-file-bound assumptions
using `--study-assumptions`. Their notices remain visible in the geometry capture
panel and survive a rerun using the same source tables. The current linear
material interpretation gives about0.195 N m per phase Arms versus the source
datasheet's0.13; this discrepancy remains explicit and is not removed by the
numerical mesh/interpolation checks. The package also retains original
datasheet/test records and source-specific licenses in `hardware_reference/`.

The updated GUI includes an explicit worker rerun with immutable source tables,
bounded inline parameters and source-hash checks. It compiles only the fixed
demonstration C controller, preserves the previous capture on failure, and drops
late results if the study changes. New source/worker/frontend code is required;
an older frozen worker candidate does not qualify these additions. No GUI
computer-use verification has been performed.
