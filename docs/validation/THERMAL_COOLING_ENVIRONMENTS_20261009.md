# Thermal cooling environments and CHT candidate evidence

Date: 2026-10-09. This is experimental candidate numerical evidence. It is not
release qualification, a representative PCB cooling prediction, or measured
hardware correlation.

## Scope and method

`scripts/validate_thermal_cooling_environments.py` executes three bounded,
independently checkable paths using original SPIKE fixtures:

1. The SPIKE steady tetrahedral solver and separately installed CalculiX solve
   the same slab with two subdivisions per axis, prescribed inward heat flux, and a
   combined convection plus diffuse gray ambient-radiation boundary. Both are
   checked against the fixture's closed-form linear temperature field. SPIKE's
   separate convection, radiation, and global heat-balance terms are checked.
2. SPIKE and CalculiX solve the existing retained two-solid contact fixture.
   Nodal temperatures and signed heat flow across each explicit contact are
   compared.
3. OpenFOAM runs the existing original heated-board/fan-air fixture through
   `chtMultiRegionFoam`. The complete inlet and outlet mass histories and the
   existing hash-bound constant-density open-flow energy histories are checked.

No external solver example, mesh, implementation, or reference result was
copied. CalculiX and OpenFOAM are separately installed runtimes under their own
licenses.

## Fixed acceptance gates

| Check | Gate |
| --- | ---: |
| Analytical, SPIKE, and CalculiX nodal temperature | maximum absolute error or pairwise difference <= 0.001 K |
| Solid contact heat flow | maximum relative SPIKE/CalculiX difference <= 1e-6 |
| SPIKE solid global energy balance | relative residual <= 1e-8 |
| OpenFOAM complete-history mass balance | maximum relative inlet/outlet mismatch <= 2e-7 |
| OpenFOAM final mass balance | relative inlet/outlet mismatch <= 1e-8 |
| OpenFOAM prescribed inlet mass flow | maximum relative error <= 1e-8 |
| OpenFOAM transient energy balance | cumulative and maximum step relative residual <= 0.01 |

The tolerances are declared in the orchestrator before solver execution. A
missing runtime returns `blocked`; saved candidate summaries are not substituted
for fresh execution.

## Actual runtime evidence

The compact accepted report is retained as
[THERMAL_COOLING_ENVIRONMENTS_20261009.json](THERMAL_COOLING_ENVIRONMENTS_20261009.json).
Its SHA-256 is
`5ec316a9e92f252b0b4f01b6e356295b1d2c18f8f919bf4ced483466bcbcfa1f`.
The larger OpenFOAM case is local at
`C:\Users\yawar\.codex\visualizations\2026\09\28\01a0e89d-245b-7a62-ba36-12913d1c9f46\thermal-cooling-validation-20261009-r3\openfoam`.
The report states `production_qualified: false` and records that its source
files remained unchanged during execution. An earlier local attempt reached
the solver but failed during report assembly because the orchestrator read a
nonexistent top-level fixture metadata field; it is not accepted evidence.

### Established solid solver comparison

- CalculiX 2.23 executed from a binary with SHA-256
  `913abf828a2d706f3e8c9da89d7a0eddd68ce817f8dabf1098cb013dfe3f94f6`.
- The combined convection/radiation slab used 27 nodes. Maximum analytical
  error was `5.6843e-13 K` for SPIKE and `4.6662e-05 K` for CalculiX. Maximum
  SPIKE/CalculiX difference was `4.6662e-05 K`.
- SPIKE separated `500.00000000000125 W` convection and
  `313.2881866497508 W` radiation from `813.2881866497501 W` prescribed inward
  heat. Its imbalance was `-1.9895e-12 W`, or `2.4463e-15` relative.
- In the two-solid contact fixture, maximum SPIKE/CalculiX temperature
  difference was `1.1369e-13 K`. Both contacts returned `-40 W` in CalculiX;
  SPIKE returned `-39.999999999999886 W`. Maximum relative flow difference was
  `2.8422e-15`.
- The cooling and contact CalculiX input SHA-256 values were respectively
  `7d99a1046e1e82381bb83e8b0c2cd58ac70e8f36e52fa41687b6db87be7774bd`
  and `f31c70c0d71442c4c9117373113bddf1d5dfa88a6364eabf9859f739384cbc89`.

These comparisons establish agreement for the stated synthetic steady solid
fixtures. CalculiX is not an independent CFD comparison and does not validate
solved airflow.

### OpenFOAM conjugate airflow execution

- Runtime: OpenFOAM v2606 in Ubuntu WSL2. `checkMesh`,
  `chtMultiRegionFoam`, and `postProcess` all returned zero.
- Fixture: one 10 mm square, 1.6 mm thick synthetic FR-4 board coupled to an
  8.4 mm air duct, eight cells per region, 0.1 W solid source, 1e-5 m3/s
  prescribed fan flow, zero gravity, laminar constant-density air,
  `dt = 0.001 s`, and `t_end = 0.01 s`.
- Runnable manifest SHA-256:
  `6c6728ee90644a69466416f8a2a403e11141d1f9785a2dc7ef8990b549cdf014`.
- Imported field artifact SHA-256:
  `6e9a85c4d37592f4be6b96e1d86476c7e95498d918a9f0ef31f34c4ebfcdac73`.
- Ten mass-history samples gave maximum relative inlet/outlet mismatch
  `1.2359e-08`, final mismatch `1.0887e-10`, and prescribed inlet-flow error
  `1.4117e-16`.
- The 0.001–0.01 s energy interval contained `9.0000e-04 J` input,
  `-4.3907e-08 J` signed boundary energy, and `9.0004390664e-04 J` stored-energy
  change. Cumulative relative residual was `9.1347e-11`; maximum per-step
  relative residual was `9.5092e-10`.
- Imported temperatures ranged from 298.1492967 K to 298.1537538 K. These
  values are field-import and range evidence only; this short run does not
  establish a steady cooling temperature or airflow accuracy.

## Explicit gaps

- The current OpenFOAM field export contains cell-centred molecular conductive
  heat-flux vectors but no hash-bound signed patch-integrated heat-flow history
  on both sides of the conjugate interface. CFD interface heat-flow closure is
  therefore `not_evaluated`. The next gate is paired patch histories with
  opposite-sign and relative-closure checks.
- The OpenFOAM energy audit begins at the first completed step, 0.001 s. It does
  not include an actual time-zero post-process baseline or audit the first time
  interval.
- The OpenFOAM case has no mesh-refinement or time-refinement sequence in this
  run. Earlier candidate summaries are not promoted by this evidence.
- The fixture excludes representative PCB copper and component geometry,
  contact materials, enclosure flow, fan curves, buoyancy, turbulence,
  radiation, heatsinks, potting, and measured boundary conditions.
- No second established CFD solver or measured airflow/temperature dataset was
  compared. Cross-solver evidence here is limited to solid conduction,
  convection/radiation boundary loading, and explicit solid contact heat flow.
- Numerical code and evidence still require knowledgeable human review before
  release. Authorship of these checks cannot grant qualification.

## Reproduction and checks

Fresh evidence was generated with:

```powershell
python scripts\validate_thermal_cooling_environments.py `
  --output <new-report.json> `
  --artifacts <new-empty-openfoam-artifact-directory>
```

The focused regression suite was run with:

```powershell
python -m unittest tests.python.test_thermal_cooling_validation -v
```

All five focused tests passed, including actual CalculiX execution. Python byte
compilation of the orchestrator and test module also passed. The first sandboxed
test attempt was blocked by denied access to the redirected Windows temporary
directory; rerunning with normal local temporary-directory access passed. An
adjacent project-Python 3.12 regression run covering the new tests, the
CalculiX thermal adapter, OpenFOAM multiregion execution and fixtures, and the
flow-energy validator passed all 35 tests.
