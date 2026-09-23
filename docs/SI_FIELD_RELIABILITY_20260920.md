# SI and cross-board reliability increment - 2026-09-20

The failed environment/suite results below are historical evidence. See the
[subsequent qualification repair](QUALIFICATION_REPAIR_20260920.md) for the
dependency, native-binary and benchmark-fixture corrections and fresh results.

This increment does not establish production or Ethernet compliance. It fixes
demonstrated defects before extending capability claims. All code and test
oracles in this increment are independently authored; no external code or
research implementation was copied.

## Corrected behavior

- PAM4 eye analysis no longer extrapolates a finite response by repeating its
  last value. Each phase uses the same genuinely observed symbol population.
  Fewer than 64 supported symbols fails explicitly; increase the waveform
  length or shorten the channel delay. Results record the observed count and
  peak delay. Pure-delay analytical regressions cover this boundary.
- Cross-board evidence screening now requires four positive completion/pulse
  and requested energy-decay records. Missing records, truncated excitation,
  insufficient decay or timestep-limit warnings fail. This is not a substitute
  for a separate time-window convergence experiment.
- Mesh comparison cannot pass when physical PML interfaces move between cases.
- The benchmark now uses nested interior grids, including width, substrate and
  copper intervals. All material and port endpoints/midpoints are retained.
  Eight fixed 3 mm PML cells lie outside a 10 mm material clearance. This is
  controlled benchmark meshing, not an arbitrary-PCB importer.

## Derivation and independent checks

For consecutive mandatory coordinates a,b in mm, the base grid uses
ceil((b-a)/h) intervals. Level L divides each of these into 2^L intervals.
Thus every coarse interior node is retained, and all interior intervals shrink
by exactly two between levels. PML cells are unchanged to isolate interior
mesh sensitivity. Tests assert nesting, boundary identity, and 2/4/8 trace
width and substrate cells plus 1/2/4 copper cells. This algebraic invariant
does not prove Maxwell convergence, skin-depth resolution or PML absorption.

For PAM4, a sample at symbol index k and phase p is admissible only if
k*samples_per_UI + peak_delay + p*samples_per_UI <= response_length-1.
Applying this bound at the largest evaluated phase gives a common population
for all phases. The delay oracle is an independently specified ideal impulse.
DFE remains known-symbol training, CDR fixed/ideal phase selection, and BER a
Gaussian proxy; this change does not add AMI or protocol qualification.

## Reproduction

Preview a mesh without running or writing artifacts:

```powershell
python scripts/run_crossboard_openems.py --output build/unused --mesh-mm 3 --mesh-level 0 --plan-only
```

Run distinct output directories for levels 0, 1, 2 with the same base spacing,
geometry, termination and time budget; the runner refuses existing output and
more than 1.5 million cells. Example:

```powershell
python scripts/run_crossboard_openems.py --output build/crossboard-nested-level0-20260920 --mesh-mm 3 --mesh-level 0 --end-criteria 1e-7 --timeout 900
```

Keep failed runs. Never reuse the old SmoothMeshLines runs as members of this
new refinement family. The historical 3/2.5/2 mm runs did not refine transverse
features and moved PML faces; their previously failed 0.02 complex-S threshold
has not been relaxed. Current-probe sampling and PML/time-window sensitivity
still require explicit verification.

## Executed evidence

- Python 3.11.9: 54 focused SI/channel/protocol, finite-record, grid, completion,
  evidence-screen and export tests passed with warnings treated as errors.
- Architecture guard passed after integration.
- Actual openEMS run: `build/crossboard-nested-level0-20260920`, four independent
  excitations, 41,344 cells, 302.15 s, unchanged source hashes and exit code 0.
  All pulses completed; final energies range -70.03 to -70.25 dB for a -70 dB
  criterion. Maximum singular value 1.0003588364 and reciprocity error
  0.0031643449 pass the unchanged 0.02 numerical screens.
  Result SHA-256: `cd6dbdc91083a55e45f87d3e30a145c5244532df4f681f343565fca53d0d1a2c`.
  No refined-grid or physical qualification is inferred from this coarse run.
- Re-screening the historical three cases retains their failed result:
  successive differences 0.04685994 and 0.04103947 exceed 0.02, and the new
  fixed-PML check also fails.
- The unqualified default Python 3.14 environment lacks jsonschema: full
  discovery ran 1,454 tests with 1 failure, 102 errors and 6 skips. This is not
  a release-pass record. The installed Python 3.11 environment is used for the
  focused validation above; no environment or dependencies were changed.
- Full Python 3.11.9 discovery completed in 295.99 s: 1,714 tests, 2 failures,
  39 errors, 2 skips. Observed blockers include missing pyarrow, an installed
  native extension lacking current planar-topology entry points (including
  canonicalize_planar_region), and the native hybrid PEEC benchmark / dependent
  CLI qualification test failing. These were not suppressed or changed by this
  increment. Native binary/source parity and the qualified test environment
  must be repaired before rerunning release qualification.

## Outstanding release work

Controlled three-level field convergence, general PCB/port compilation,
geometry-matched measured correlation, receiver/CDR/BER qualification,
distributed backend qualification, general actuator validation, and full
thermal/airflow qualification remain separate open work. A corrected benchmark
or passing unit suite must not enable these claims automatically.
