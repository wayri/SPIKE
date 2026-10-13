# Thermal 3D presentation and solid-source integration

Date: 2026-10-10. Experimental development evidence; no production or Siemens
accuracy equivalence is claimed. The installed Windows application was not
updated by this verification.

## Changes

- Saved layered temperatures occupy physical top and bottom PCB faces by
  default. Internal saved depth fields require explicit inspection. Ordinary
  PCB layer separation no longer creates a floating thermal stack.
- Bottom probes identify the saved bottom layer and physical depth. Plate
  results expose the absence of an independently solved underside field.
- Occurrence rendering keeps the source-board centre separate from the active
  viewport centre; temperature data are not recentered onto another board.
- Component STEP promotion supports a reviewed batch. Each component preserves
  its model identity, mounting transform and material. Promotion remains explicit.
- The Thermal solid-study button requests Coupled studies directly, without
  overriding later manual section navigation on unrelated snapshot updates.
- A body-power form assigns reviewed watts to an exact meshed occurrence.
  Existing target-body sources need explicit replacement; other bodies remain
  unchanged. Geometry changes and edits invalidate old results.

## Numerical authoring invariant

The Python worker uses the already admitted total body volume V in m³ and
assigns a uniform source density q = P/V in W/m³ to every tetrahedron.
Therefore sum(q × V_cell) = P. Unequal cell volumes receive different powers,
not equal watts per cell. The handoff owns mm-to-m conversion and tetrahedron
admission. This is a uniform package source assumption; die geometry, electrical
loss and junction temperatures are not inferred. Original implementation and
analytical oracle; no external implementation was copied.

Six focused Python tests cover unequal volumes, unit conversion, an actual
thermal solve with conserved source watts, exact occurrence ownership,
replacement and zero removal, stale/invalid inputs and worker dispatch.
UI lifecycle tests cover review, errors, stale responses, invalidation, duplicate
clicks and unmount ownership. Numerical source authoring requires knowledgeable
human review before release.

## Established solver checks executed

15 Python 3.11 tests passed using the admitted local Gmsh OCC runtime, including
real STEP component placement, joint contact/gap/overlap admission and package
MNA–CalculiX electrothermal feedback. A separate cooling test run exercised the
existing real CalculiX analytical cooling/interface comparisons. These original
small fixtures do not establish representative hardware accuracy.

Browser WebGL acceptance used production BoardViewport with the checked-in
eBrake1 board and retained layered result. Distinct top/bottom patterns, retained
component visibility, separation without thermal explosion, explicit internal
inspection and plate bottom-unavailable behaviour were observed. This is browser
runtime evidence, not packaged/native desktop visual acceptance.

## Remaining scope

Both solid solve admission paths remain bounded to 5,000 tetrahedra and 10,000
nodes; joint meshing admits 64 source solids. Arbitrary multi-solid STEP packages
need explicit supported decomposition. Solids require materials, placement,
contacts, loads and cooling before solving; decorative display meshes alone
are insufficient. Passive solids participate through conduction without
artificial heat sources.

Static air/forced-air coefficients and ambient radiation are imposed boundary
models. Generic imported assembly airflow, buoyancy, turbulence and air-temperature
fields need a fluid-domain compiler plus validated conjugate heat transfer.
Existing channel/constructed duct examples do not provide that general workflow.
Potting/coating need resolved reviewed material volumes or an admitted thin-layer
model; material names alone do not create geometry. Heatsinks need real contact
interfaces. See [meshing and cooling workflow](../ASSEMBLY_THERMAL_MESHING.md)
and [QuickTherm comparison](../QUICKTHERM_PACKAGE_COMPARISON.md).

## Integration gate outcome

TypeScript, architecture/control standards, parser, thermal presentation,
assembly-workspace/navigation, body-power/lifecycle and production Vite build
checks passed. Cargo reported 44 passed and one ignored test.

The full Python discovery ran 3,063 tests in 872.082 s: 3,036 passed, 26 skipped,
and one failed. `test_python_debug.test_parent_admits_design_bound_result`
remained in `starting` beyond the existing four-second deadline during that run.
All eight debugger tests passed on isolated recheck in 29.794 s with unchanged
thresholds. The aggregate run is therefore recorded as failed, not green;
startup timing under concurrent workload remains an unresolved regression gate.
Logs are local at `output/thermal-integration-python-tests.log` and
`output/thermal-integration-debug-recheck.log`.

The temperature legend shares the renderer's exact saved range and palette.
The latest retained browser screenshot is local at
`.tmp/thermal-surface-acceptance/layered-bottom.jpg`; the 25.74–50.06 °C legend
and model-status notice occupy separate lanes.
