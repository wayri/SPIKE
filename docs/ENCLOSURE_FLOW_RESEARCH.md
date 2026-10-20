<!-- SPDX-License-Identifier: Apache-2.0 -->
# Enclosure momentum, turbulence and rotation development

The executable enclosure workflow is [CHT v2](ENCLOSURE_CHT_REFINED.md):
stationary voxel obstacles, inertial laminar flow and actual momentum/heat
re-solving on manually selected rectilinear cuts. Cuts propagate planes through
the box; this is not confined patch/octree AMR. Re <=20, numerical budgets,
convergence checks and failed-result field suppression remain enforced.

Separate in-process research APIs test the next mathematical pieces:

| API in `python/spike_core` | Executed operation | Explicit exclusion |
| --- | --- | --- |
| `enclosure_symmetric_stress.solve_enclosure_symmetric_stress` | Coupled velocity/pressure with prescribed positive cell viscosity and full symmetric strain | Obstacles, transported closure and material-law qualification |
| `enclosure_sa_transport.solve_enclosure_sa_transport` | Nonlinear positive-branch SA-noft2 transport at supplied divergence-free velocity | Coupled RANS, general wall-distance geometry and engineering turbulence |
| `enclosure_rotating_frame.solve_enclosure_rotating_frame` | Whole-frame Coriolis momentum and centrifugal physical pressure | Rotating blades, stationary/rotating interfaces, propeller loads and moving meshes |
| `enclosure_rans_research.solve_enclosure_rans_research` | Same-state coupled mean/positive-SA equations with independently manufactured sources | Engineering turbulence, open boundaries, complex obstacles and turbulent CHT |
| `enclosure_flow_analysis.analyze_enclosure_flow` | Flux-preserving probes and cell-exact traces of admitted supplied stationary MAC fields | New PDE solution, arbitrary meshes, unsteady pathlines, curl/Q and viewer integration |

These return explicit experimental/research scope and
`production_qualified:false`. They are intentionally not advertised as new
worker engines. Rotation retains the relative-flow Re <=20 limit and additionally
limits the rotation number to 20. Prescribed viscosity must not be used to hide
a molecular Reynolds-number violation when developing future closure coupling.
Only the explicit coupled research module composes mean momentum and SA.
No CHT/rotation/FSI composition is inferred.

## Reproducible mathematical benchmarks

From the repository root, using an environment with the existing NumPy, SciPy
and jsonschema dependencies:

```powershell
python -Werror scripts/benchmark_enclosure_prerequisites.py --output build/my-flow-evidence
python -Werror scripts/benchmark_enclosure_cht_v2.py --output build/my-cht-evidence
```

Both output directories must be fresh. The first retains the full assertion log,
test outcomes, source digests, interpreter/dependency identity and elapsed time.
It fails on any skipped/expected-failure test, assertion error or source change
during execution. The second retains exact public requests/results and their
digests. A receipt is execution evidence, not a universal accuracy certificate.
Elapsed time is not a qualified performance/scaling claim.
The [executed benchmark record](validation/ENCLOSURE_FLOW_BENCHMARKS_20261020.md)
retains the current test partitions and receipt identities.
The later [21 October increment](validation/CFD_CAPABILITY_INCREMENT_20261021.md)
adds the coupled-equation/field-analysis suite and retained-JSON replay:

```powershell
python -Werror scripts/benchmark_cfd_capability_increment.py --output build/my-coupled-flow-evidence
```

The assertion fixtures also show complete built-grid API inputs without
inventing a real enclosure or fan model:

```python
from tests.python.test_enclosure_rotating_frame import manufactured
error, result, request = manufactured(8)
assert result["status"] == "completed"
print(error, result["diagnostics"])

from tests.python.test_enclosure_sa_transport import manufactured_request
from python.spike_core.enclosure_sa_transport import solve_enclosure_sa_transport
request, exact = manufactured_request(8, q_amplitude=1.92)
result = solve_enclosure_sa_transport(request)
assert result["status"] == "completed"
print(result["diagnostics"])
```

These are manufactured mathematical fields and forcing, **not predictions of
physical turbulence or propeller performance**. Source and units are derived in
the [stress](validation/ENCLOSURE_SYMMETRIC_STRESS_20261020.md),
[SA](validation/ENCLOSURE_SA_TRANSPORT_20261020.md) and
[rotation](validation/ENCLOSURE_ROTATING_FRAME_20261020.md) method records.
Independent continuum derivatives, dimensional-scaling cases, exact energy
identities and deliberately wrong-operator controls supplement residual checks.

## Remaining acceptance work

The quadratic-viscosity coarse 4/8/12 study missed its original >1.8 order
gate. That interval remains unqualified; an additional 8/12/16 study passed the
same threshold. Re-entrant obstacle finest velocity error is about 10.4%, not
general 2% accuracy. Neither limitation is erased by passing the bounded suite.

Bounded closed-box joint momentum/SA verification is recorded in the
[coupled method record](validation/ENCLOSURE_RANS_RESEARCH_20261021.md).
The [field-analysis record](validation/ENCLOSURE_FLOW_ANALYSIS_20261021.md)
derives conservative reconstruction and its limitations. Next are general-flow
joint residual qualification, nontrivial wall-layer and
separated-flow reference cases, geometric wall distance, turbulent heat-flux
closure and physical correlation. Rotating propellers additionally require
blade geometry, rotating/stationary interfaces or conservative ALE, mesh-motion
geometric conservation, torque/thrust/work balance, spatial/time convergence and
independent or measured propeller cases. See the detailed
[requirements](validation/TURBULENCE_ROTOR_REQUIREMENTS_20261020.md).
No current gate or capability flag has been removed to substitute for that work.
