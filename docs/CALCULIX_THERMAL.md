# CalculiX thermal extension

SPIKE's original Apache-2.0 adapter executes a separately installed CalculiX
CrunchiX process. It does not include CalculiX source, binaries, or upstream
examples. Consult the installed distribution's license and the
[upstream project](https://www.dhondt.de/) before redistribution; upstream
publishes GNU GPL v2 terms separately from SPIKE's license.

## Workflow and scope

Prepare a retained assembly thermal field request and thermal problem using
the existing assembly mesh/boundary editor. Select CalculiX for the external
thermal run. Its extension contributions are `calculix-thermal` (preflight),
`calculix-thermal-prepare` (deck preview), and `calculix-thermal-run` (execution).
No generated or imported arbitrary solver script can be executed by this path.

Install CalculiX independently. The worker discovers `ccx` on PATH and a small
set of conventional Windows installation paths, including
`C:/msys64/ucrt64/bin/ccx.exe`. For another installation, set the local environment
variable `SPIKE_CALCULIX_EXECUTABLE` to an absolute executable path and restart
SPIKE. An explicitly configured missing executable fails discovery instead of
silently selecting a different installation. Runtime detection alone does not
qualify physics. The adapter reports executable identity and version for an
actual completed run. No runtime download or installation occurs in the adapter.

Supported experimental physics:

- Straight-sided conforming four-node tetrahedra with constant symmetric
  positive definite conductivity, including rotated anisotropy already bound
  by the assembly handoff.
- Prescribed temperature, inward heat flux, volumetric heat generation,
  convection to a prescribed ambient, diffuse gray radiation to a prescribed
  radiation temperature, and combined convection/radiation.
- Explicit retained thermal contacts on congruent coincident triangles with
  user-supplied conductance and separately indexed bodies. Contact conductivity
  is fixed and pressure independent. No mechanical displacement is solved.
- Every connected thermal component needs a temperature or ambient sink.
  Unspecified exterior faces are recorded as adiabatic.

Unsupported inputs fail admission. These include transient heat transfer,
temperature-dependent materials, moving/nonmatching contact, inferred package
physics, solved fluid flow, and cavity radiosity. The UI and this extension do
not promote visual component models into solid physics automatically.

## API and contracts

`python/spike_core/assembly_field_thermal.py` owns shared pure occurrence
binding through `bind_assembly_field_thermal(request, problem)`. Both the
internal thermal solver and the external adapter reuse it. It returns the
handoff, admitted tetrahedral request, assigned boundary IDs and contact face
IDs; it does not execute a solver.

`python/spike_core/calculix_thermal.py` exposes:

- `prepare_calculix_thermal(request, problem)`: deterministic SI deck,
  node/element/material/boundary/contact maps, source traceability, source
  digests and runtime availability in `spike/calculix-thermal-case/v1`.
- `run_calculix_thermal(request, problem, engine_options=None)`: actual external
  temperatures in `spike/calculix-thermal-result/v1`. Allowed options are only
  `timeout_seconds` (1 to 3300; default 300) and `threads` (1 to the lesser of
  available CPUs and 32; default 1).
- `verify_calculix_thermal_result(request, problem, result)`: saved-result
  integrity/staleness and field ownership checks. Digest admission is not
  cryptographic proof that a solver ran.

The nested field uses `spike/calculix-thermal-field/v1`; it contains Kelvin
temperatures, per-cell Fourier heat flux derived from these returned values,
and contact heat transfer derived from the retained conductance. These derived
quantities are labeled explicitly. There are no invented CG counts, internal
solver residuals, or heat-balance claims. `diagnostics.global_heat_balance` is
`not_reported`. All results remain experimental and not production qualified.

The extension process returns the usual `spike/extension-result/v1` envelope;
the completed run lives in `data.result`, and prepared cases in `data.case`.
The run contribution declares the dedicated thermal result output contract
for host admission. The mesh/occurrence frame, source IDs, material IDs,
boundary IDs, contact IDs and problem digests remain bound through preparation,
execution and saved-result admission.

## Numerical translation and evidence

### DC electrothermal iteration

`run_assembly_electrothermal` also accepts optional `thermal_engine` values
`internal` (the backward-compatible default) and `calculix`. Optional
`thermal_engine_options` accepts the same bounded CalculiX timeout/thread
controls; executable paths and commands are rejected. Internal engine requests
cannot carry external runner options. Each external thermal phase actually
runs CalculiX with that iteration's deposited electrical and device losses.
The next internal electrical phase evaluates its declared conductivity law at
the returned temperatures. No fallback to internal thermal execution occurs
when CalculiX is missing or fails.

Each iteration checks the unrelaxed temperature defect and electrical power
feedback defect. The result retains the last executed `thermal_problem`, each
iteration's thermal result digest, the original coupled request digest, and the
actual final CalculiX result with executable/deck/output evidence. CalculiX
results report `conservation.thermal_imbalance_w: null` and
`thermal_balance_status: "not_reported"`; electrical conservation and feedback
defects remain independently reported. Fixed-point tolerances describe the
returned finite-precision NT samples, not a bound on discretization error.

Matched thermal links are admitted before any electrical solve. Retained area
must equal the sum of matched triangle areas; a supplied thermal resistance
must satisfy R=1/(h*A). Missing or contradictory links are rejected. A contact
does not create a solder joint, package material or physical volume by itself.

The optional Python cancellation callback is checked between coupled phases
and during a running CalculiX process; cancellation kills the active external
process and returns no result. Each thermal phase has a separate timeout;
the coupled iteration remains capped at 50 phases. There is no claim that a
steady DC conductivity solve provides AC SI loss extraction or a switching
circuit transient.

`tests/python/test_calculix_electrothermal.py` verifies an actual two-board
2 V series-conduction case: two 0.5 ohm volumes and a 0.25 ohm contact yield
1.6 A and 3.2 W, including 0.64 W contact heat. Returned CalculiX temperatures
agree with the independent internal thermal implementation within 0.0002 K
for this fixture. Temperature-dependent feedback, nonconvergence, malformed
options, missing runtime, mismatched contact metadata and stale thermal loads
are checked separately. This does not qualify arbitrary hardware models.

### Deck and runtime

The compiler converts mesh lengths to metres once. Conductivity is W/(m K),
volumetric loading W/m3, inward surface flux W/m2, convection/contact conductance
W/(m2 K), and temperatures Kelvin. It emits `DC3D4`, `*CONDUCTIVITY,TYPE=ANISO`,
`*HEAT TRANSFER,STEADY STATE`, `*DFLUX`, `*FILM`, and `*RADIATE` as applicable.
The Stefan-Boltzmann constant is 5.670374419e-8 W/(m2 K4), and absolute zero is 0.
Contacts use `*GAP CONDUCTANCE`, `*CONTACT PAIR,TYPE=SURFACE TO SURFACE` and zero
clearance, after SPIKE has proved coincidence and opposite outward normals.
Unit mechanical slope/tension values satisfy the parser's required interaction
syntax; this pure thermal analysis has no mechanical solution or pressure claim.

The fixed linear solver is `ITERATIVE CHOLESKY`. During development, the MSYS2
2.23 default PaStiX backend stalled on a nine-equation slab. Explicitly selecting
the documented iterative backend completed the same case immediately. A
timeout still bounds execution independently of solver convergence.

Execution occurs in a fresh temporary directory with fixed job name and argv,
`shell=False`, no stdin, and a hidden Windows process. Input admission caps
10,000 vertices and 5,000 tetrahedra and bounds topology work. Output files are
monitored with a 32 MiB aggregate cap; elapsed time and CPU thread count are
bounded. Completion requires zero exit status, no `*ERROR`, a solver completion
marker, a final end-time-1 temperature table, and exactly one finite nonnegative
temperature for every admitted node. Prescribed temperatures must agree within
the documented decimal output precision. Input/output/log/executable SHA-256
hashes are retained, along with the actual solver version and log tail.

Run the deterministic and executable tests with:

```text
.venv/Scripts/python.exe -m unittest tests.python.test_calculix_thermal -v
```

The executable tests skip only if no installed executable is found; failures
from an installed runtime fail the tests. On 2026-10-06 the signed MSYS2 UCRT64
CalculiX 2.23 runtime passed analytical conduction, convection, combined
convection/radiation, a three-grid volumetric heat-source convergence check,
and a two-body matched-contact check. The contact oracle has two 1 m slabs with
k=2 W/(m K), contact h=4 W/(m2 K), unit area, and 300/400 K endpoints. Series
resistance is 1.25 K/W: the 80 W heat flow gives 340/360 K interface values.
Tests also check SI scaling, material and face numbering, malformed output,
missing runtime, unsafe options, stale saves, altered fields and invalid geometry.

These synthetic oracles verify the admitted model translation. They do not
validate arbitrary PCB/enclosure meshes, material estimates, natural convection
coefficients, hardware temperatures, or mesh convergence for a user's assembly.
Knowledgeable human review of numerical code remains required before release.

## Method provenance and clean-room statement

Only public card documentation informed the original adapter. No upstream
implementation, comment, fixture, example deck or data was copied or adapted.
Fixture meshes and analytical oracles are original SPIKE material. Invariants
come from Fourier conduction, the Robin convection law, Stefan-Boltzmann
radiation, and thermal resistance in series. Authoritative card documentation:

- [CalculiX project and current manual](https://www.dhondt.de/)
- [Conductivity tensor component ordering](https://web.mit.edu/calculix_v2.7/CalculiX/ccx_2.7/doc/ccx/node174.html)
- [Steady heat transfer and solver selection](https://feacluster.com/CalculiX/ccx_2.18/doc/ccx/node285.html)
- [Distributed flux, tetrahedron face numbering and sign](https://www.feacluster.com/CalculiX/ccx_2.18/doc/ccx/node253.html)
- [Prescribed ambient radiation](https://www.feacluster.com/CalculiX/ccx_2.18/doc/ccx/node316.html)
- [Thermal contact conductance](https://www.feacluster.com/CalculiX/ccx_2.18/doc/ccx/node279.html)
- [Contact-pair definition](https://feacluster.com/CalculiX/ccx_2.18/doc/ccx/node236.html)
- [Surface interaction admission](https://www.feacluster.com/CalculiX/ccx_2.18/doc/ccx/node337.html)
- [NT temperature output](https://feacluster.com/CalculiX/ccx_2.18/doc/ccx/node307.html)

The adapter canonicalizes AssemblyIR defaults after raw input admission. Saved
field records retain that canonical request so project reopening and volume
visualization share identical geometry/material/result bindings.
