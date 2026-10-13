# Retained-volume assembly EM

The experimental OpenEMS path executes explicitly conductor-resolved retained
assemblies, including polyhedral enclosure cavities. It preserves material
interfaces and closed outward surfaces, without substituting bounding boxes.
It does not extract copper from mechanical STEP board outlines.

## Contract and workflow

`spike/assembly-em-request/v1` contains `geometry`, `ports` and `settings`.
Geometry is an admitted `spike/assembly-field-handoff-request/v1`, domain `em`.
Every occurrence has tetrahedral material volumes and explicit exterior
conductor-face ports. Start attaches to the declared return face; stop attaches
to the signal face. Both terminal rectangles must fit their triangles, and
intervening conductor contact is rejected. Exactly one port is excited.
Reflected voltage ratios scale by sqrt(R_excited/R_output) for power-normalized
S-parameters. The returned column is not a complete multiport matrix.

Settings supply increasing `frequency_hz`, `mesh_resolution_m`, `air_margin_m`,
`max_timesteps`, `end_criteria`, `timeout_s` and `threads`. Coordinates are metres.
Six-sided PML has eight cells per side. Axis/cell budgets are checked before
allocation; the final grid passes memory, wavelength, clearance and conservative
one-cycle CFL-window screens. These checks do not establish numerical accuracy.

Worker methods: `prepare_assembly_em`, `run_assembly_em` and
`admit_assembly_em_study`. Heavy-worker supervision keeps execution off the UI
thread. In Tools, open **Retained assembly EM · OpenEMS** to validate or execute
an explicit request, inspect its port response and activate saved fields with
one click. The study persists inside `.spike`; activation checks its input
digests and exact physical assembly before rendering. The CLI retains a new run
directory:

```powershell
.venv/Scripts/python.exe -m python.spike_core.cli assembly-em --request study.json --run-dir output/new-assembly-em
.venv/Scripts/python.exe scripts/run_retained_assembly_em_benchmark.py --output output/new-enclosed-em-benchmark
```

Immutable trusted source and finite data go to the isolated runtime through
stdin. Editable case scripts are not executed. Existing process-tree timeout,
bounded logs and a 512 MiB output quota apply. Results bind the full request,
compiled geometry and fresh invocation ID; XML/HDF5 artifacts receive SHA-256
hashes. Failed runs retain diagnostic logs.

## Fields and validation limits

E/H HDF5 fields retain cell-interpolated raw Gaussian-pulse DFT at the highest
sweep frequency. A bounded embedded preview divides complex E/H samples by the
incident voltage pulse DFT for **1 V peak incident** normalization (V/m and A/m).
Raw pulse-transform units remain V·s/m and A·s/m. This is not 1 W normalization.
Results retain metre axes, shape, native sample IDs and subsampling; displayed
volume samples do not fabricate surfaces between samples. Material
boundary interpolation and thin-metal skin/roughness losses need qualification.
A normal exit alone does not prove energy-decay or duration convergence.
Results remain `unvalidated`, `production_qualified: false`.

### Exact stopping evidence (ACC03, 13 October 2026)

New results separate `execution_status`, `stopping` and
`observable_sensitivity`. The bounded native-log parser records the requested
decay ratio/dB, observed decay and sample timestep, actual final iteration count
when a native summary exists, cap detection, stopping reason and runtime
identity. A timed-out progress sample is not an actual final count. Missing,
truncated, malformed, nonfinite, stale or configuration-conflicting evidence
cannot establish requested-decay success. A successful decay observation must
match the terminal iteration count; absence of a cap warning is not success.

The parser is line/token bounded and tested against hostile numeric and repeated
marker cases. `termination` remains a compatibility projection, not a stronger
qualification statement. A single run's observable sensitivity is
`not_assessed`; a paired validation reports its own sensitivity test separately.

Fresh five-case evidence is retained under
`output/retained-assembly-em-acc03-20261013`. Its duration run completes but fails
the requested -90 dB stopping criterion at 80,000 steps (-81.74 dB observed).
The corresponding maximum complex-S11 change passes independently:
3.09834e-5 <= 1e-4. Corrected-parser reinterpretation is retained separately as
`stopping-reparse-v2.json`; original run records and failed evidence were not
overwritten. A separate timeout probe retains unknown final count and decay
achievement. The canonical duration-only comparison is now
`duration_refined_capacitance_relative_error`; its historical `time_refined`
alias explicitly says it is not timestep refinement. Independent timestep and
field/loss accuracy studies remain ACC08 work.

Original geometry oracles cover oriented volume, cavities, placement and simplex
intersection. The [independent finite-enclosure reference](RETAINED_EM_INDEPENDENT_REFERENCE.md)
records spatial, PML-distance, duration and normalization checks. Its final
capacitance discrepancy is 2.36% and maximum gap-field discrepancy is 4.91%.
Those bounded plate/cavity checks do not qualify Arduino board geometry,
dissipative losses or field convergence.
No connector/harness extraction, nonlinear magnetics, thermal feedback or EMI
compliance is implied. Knowledgeable numerical human review precedes release.

## Existing enclosed Arduino report

The October 10 report has three homogeneous mechanical solids, no EM ports and
an admission-only enclosure with zero conductivity. Retained boards lack physical
stackup/fill data and include unqualified drilled/custom padstacks. That case is
still not a solved routed-board EM study. It requires copper-resolved volumes,
verified material/stack parameters, connector geometry and explicit excitation.
The original conducting-plate/hollow-case benchmark exercises execution without
substituting it for the Arduino geometry. Metadata handoff remains non-executable;
the separate execution contract performs its own physical and resource admission.

## Provenance

Original compiler, runner and fixtures; no external implementation/examples copied.
API documentation only:
[polyhedra](https://docs.openems.de/en/latest/python/CSXCAD/CSPrimitives/CSPrimPolyhedron.html),
[dumps](https://docs.openems.de/en/latest/python/CSXCAD/CSProperties/CSPropDumpBox.html),
[ports](https://docs.openems.de/en/latest/python/openEMS/ports.html).
