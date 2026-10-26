<!-- SPDX-License-Identifier: Apache-2.0 -->
# Curated promo projects for SPIKE 0.4.2

These seven complete saved frontend snapshots open from Work examples through
the normal project loader and unsaved-changes guard. Opening does not run a
solver. The snapshots contain the full existing request/result arrays; their
past executions remain experimental or approximate and are not hardware,
convergence, release or installed-application qualification.

Original SPIKE-owned inputs, generated meshes/results and the two original UI
captures are Apache-2.0. Preserve LICENSE, NOTICE, DEMO_BOARD_PROVENANCE.md and
provenance.json when sharing. No Arduino/CC BY-SA boards, CERN-licensed board or
motor derivatives, third-party model binaries, solvers or compilers are copied.

| Project | Saved scope and next action |
| --- | --- |
| ebrake-transient.spike.json | Owner-authorized EBrake source, layered thermal inputs, 16 saved board frames from 0 to 600 s. Thermal workspace: inspect layered board thermal setup and scrub saved frames. Part case/junction estimates are steady values. |
| case-contact.spike.json | Original homogeneous PCB/hollow case solid-thermal mesh, finite contact h=500 W/(m2 K), 25 saved frames over 120 s. Multi-board: open Assembly volume field study. Board peak 303.413 K. |
| poor-contact.spike.json | Same power and outside cooling, contact h=5 W/(m2 K), full saved solid-thermal history. Board peak 318.876 K. |
| planar-pm.spike.json | Original prescribed-current planar PM FEM study, final returned field and angle/torque histories. EM / Machines / Geometry field study. No controller or shaft-time coupling is asserted. |
| motor.spike.json | Original reduced voltage-driven PM DC motor response and energy ledger. EM / Machines / Parameter reference models. Separate from planar FEM. |
| electromagnet.spike.json | Original linear reluctance reference using supplied relative permeability 2000. No geometry-resolved PCB inductor extraction. |
| electromagnet-air.spike.json | Same reduced reference with supplied relative permeability 1. Compare the returned reference quantities. |

The EBrake snapshot is about 6 MiB, the explicit exception to the preferred
4 MiB project budget so its source and actual frames remain complete. Other
projects are below 4 MiB; this whole curated directory stays below 20 MiB.
The catalog allows 8 MiB only for explicitly declared project snapshots and
512 KiB for ordinary text. Assets load on demand. Inspecting a large snapshot
shows a bounded excerpt; saving or opening uses its full unchanged text.

The case snapshots preserve the thermal volume mesh and complete results.
Their CAD model index retains the original package: STEP reference. That
reference cannot resolve from a frontend JSON snapshot alone. The exact
original-case.step companion is included for explicit relinking if CAD display
is wanted. Saved volume results do not require that CAD relink. EBrake component
model binaries are not included; board geometry and thermal cells are retained.

Illustrative materials, loads and cooling are unmeasured. The case cavity has
no solved air; convection is a boundary condition, not CFD. No new mathematics,
solver, runtime, autorun, controller compilation or publishing is added.

solenoid-request.json is a setup-only request for the original stationary
nonlinear planar solenoid. The complete source result projection exceeds
14 MiB and is deliberately omitted. Run its source workflow explicitly from
the checkout if needed; do not infer a completed bundled solenoid execution.
The EBrake virtual-sink comparison and larger PI/SI, drone, ESC, chamber,
converter and propulsion packs remain in the original collection. See
ORIGINAL_START_HERE.md and output/SPIKE-All-Projects-20261025/OPEN_PROJECTS.html
in the checkout for scope, source obligations and incomplete work. The real
propulsion loop remains incomplete; the collection is not bundled here.

## Pictures and capture boundaries

pictures/electric-field-lines.png and magnetic-field-lines.png are unchanged
25 October browser-preview captures of the beta BoardViewport component,
not captures or acceptance evidence of the installed desktop application.
They depict original two-substrate box geometry with existing real openEMS
1.5 GHz samples. VTK generates frozen-phase field lines from those vectors.
Each field's colors are independent relative amplitudes because the raw pulse
DFT absolute-unit ambiguity is unresolved. Lines are presentation curves, not
wave propagation or solver-returned paths. These figures are a separate guide;
they are not fields of the EBrake, case or machine projects.

capture-verification.json retains the original image hashes and capture mode.
field-line-execution.json and FIELD_LINE_METHOD_REVIEW.md preserve the source
hash, method and limits. Full field arrays are in the original artifact pack,
not this picture guide. No screenshot is evidence of a new solver execution.

## Reproduce and verify the curation

With the retained original output/promo-showcase-20261023/READY_TO_OPEN pack
available locally, run `python -m examples.promo_release.build` from the source
checkout. That original output collection is not included in this compact
directory; its builders and source workflows are under examples/promo_showcase.
The checked-in snapshots remain complete for offline review without rebuilding.
It reads the original native v3 packages with read_project, hydrates all saved
result artifacts, applies the existing frontend_project_payload projection and
serializes it without removing arrays. provenance.json records exact source
ZIP SHA-256, manifest payload digest and snapshot SHA-256/byte counts. Python
tuple-to-JSON-array normalization is the only serialization change. The builder
also checks image identities against the original capture receipt and bounds
the total payload. It executes no solver.

From app, run `npm run test:work-examples`. It checks complete asset allowlists,
hashes, budgets, normal project-parser admission, selected project dispatch,
save/inspect, filters and action failure recovery. Native visual and installed
package checks remain separate from these deterministic checks.
