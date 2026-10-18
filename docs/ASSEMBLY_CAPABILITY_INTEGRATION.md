# Assembly thermal capability integration

## Status on October 10, 2026

The internal solid thermal solver no longer has the former 5,000-cell ceiling.
Generated coating and potting solids are retained in the portable project.
The assembly airflow adapter compiles retained solid geometry and a surrounding
air domain into conforming OpenFOAM regions. **Native airflow execution has not
been validated in this session: WSL is unresponsive. General curved coating is
also unfinished.** These changes do not establish production qualification.

## Desktop workflow

1. Open a saved assembly and its assembly thermal field editor. Read retained
   geometry and layers. Promote required component STEP references to physical
   parts; a visible model alone is not included in the solve.
2. Assign reviewed conductivity and provenance to every physical material.
   In **Physical coating and potting volumes**, choose bodies and thickness for
   a coating, or supply world-coordinate fill bounds for potting. Enter the
   encapsulant conductivity and its property source.
3. Generate volumes. A successful generation retains new STEP bytes, model
   hashes, material records and assembly occurrences inside `.spike`, preserving
   unrelated members and invalidating previous results. Consumed recipes are
   removed from the saved generation setup to prevent duplicate solids.
4. Reload the assembly. For solid thermal, assign heat sources, contacts and
   exterior boundaries before solving. Generated bodies have no invented heat
   load or mounting resistance.
5. For airflow, use **Use reviewed materials for assembly airflow**, then load
   current assembly sources. Supply an enclosing air domain, solid density and
   heat capacity, air properties, watts and time settings. Select static air
   conduction, bounded Boussinesq natural convection, or prescribed inlet flow.
   A flow rate is not a solved fan curve or turbulence model.
6. Touching solids require explicit acknowledgement of perfect thermal contact.
   Finite thermal-contact resistance is not supported by this airflow adapter;
   use the solid solver for studies requiring those resistance values.
7. Run and save airflow only with an available admitted OpenFOAM runtime. Saved
   temperature and velocity samples load directly from the project. Slice and
   region controls show computed cell centres with millimetre coordinates and
   K or m/s units; the view does not interpolate missing values.

## Geometry and resource limits

- Coating: proved for local box-shaped bodies with arbitrary rigid placement.
  Expanded-box subtraction creates mitered corners, not rounded constant-distance
  offsets. Irregular and curved STEP surfaces are explicitly blocked: the pinned
  native OCC offset/boolean path crashes on those cases. No approximate shell is
  substituted.
- Potting: an explicit polygon-prism fill minus retained bodies and supplied
  exclusions. The guided UI supplies rectangular bounds; the API supports the
  admitted polygon-prism recipes. Result must be one connected closed solid.
- Airflow: retained single STEP solids, supported polygon prisms and tubes,
  rigid occurrence transforms, enclosed air domain, conforming region interfaces.
  Each region compacts its own mesh points. Floating heatsink-role regions are
  rejected; heatsink mounting records use actual shared interfaces.
- Solid thermal: maximum 100,000 cells/nodes, 512 MiB estimated workspace,
  4 million sparse entries, bounded geometry comparisons and traversals.
  Transient output retains its separate 200,000 saved-value budget. Existing
  handoff serialization is limited to 8 MiB, so large detailed meshes can be
  rejected before reaching the count ceiling. Electrical limits are unchanged.
- Project airflow result: 32 MiB saved/transport budget. Result/request hashes,
  retained geometry and manifest identity are checked before admission. Package
  replacement checks the expected manifest under a cross-process write mutex.

## Headless and LLM interface

Fixed worker methods and corresponding MCP tools are available:

| Worker method | Inputs beyond project identity |
| --- | --- |
| `read_assembly_airflow_setup_in_project` | `assignments`, `mesh_options` |
| `run_assembly_airflow_in_project` | `assignments`, `mesh_options`, `request` |
| `read_assembly_airflow_study_in_project` | None |
| `run_assembly_airflow` | Direct reviewed `request`, without a project save |

Project identity means `project_path` and
`expected_manifest_payload_sha256`. The setup read returns retained solids,
source ownership and required properties. The run request must preserve those
solids and mesh inputs. External local STEP paths cannot replace package sources
through the project service. Missing or stale results remain absent/stale rather
than opening old fields as current.

## Evidence and remaining acceptance

Original analytical slab reference: 10,368 tetrahedra, maximum temperature error
2.65e-10 K and reported residual 7.44e-13. A 6,000-tetrahedron transient uniform
heating reference checks heat capacity and time evolution. A 10,374-cell body
heat case balances 7 W deposited against a −7 W reaction, with peak 301.75 K.
These tests extend capacity; they do not add new thermal physics.

Generated coating/potting volume oracles: expanded 2×2×1 mm box with 0.2 mm
coating gives 4.064 mm³ shell volume; 4×4×3 mm potting fill minus the original
box gives 44 mm³. Existing reviewed contact solves conserve imposed heat to
less than 7e-15 W. Actual portable coating and potting projects reopen with
verified STEP hashes and regenerate without duplicate recipes.

Affected solid, transient, airflow admission, native exporter, project and MCP
regression group: 66 tests passed. Encapsulation persistence group: 6 tests
passed. TypeScript, airflow control tests, shared button standards and the
architecture guard passed. Runtime evidence is in the local
`output/assembly-capabilities-20261010` directory.

The prepared retained-board/case airflow mesh has 6,497 tetrahedra and 1,473
vertices; maximum solid CAD/mesh volume discrepancy is 0.00355%. This is geometry
evidence, not a solved airflow/air-temperature result. Native static, natural
and forced cases still need mesh checks, convergence, heat/flow conservation and
reference comparisons after WSL recovers. Native window visual acceptance is
also pending. Cancelling the Windows proxy has not proved immediate termination
of WSL solver descendants; do not claim complete cancellation containment.
Knowledgeable numerical review remains required before release.

## Conservative geometry-to-CHT source admission (October 18, 2026)

Before writing an OpenFOAM case, `assembly_airflow_admission.py` now checks the
mesher's explicit millimetre units, complete `solid_N` to retained-source mapping,
requested cell/vertex limits and positive tetrahedron orientation. Missing solid
or air cells, duplicate tetrahedra/coordinates, invalid indices, nonfinite values
and ill-conditioned tetrahedra are rejected. Each region volume is recomputed
from its vertices; the reported volume must agree to a relative 1e-9. Solid
volumes must also remain within the existing 2% CAD tessellation tolerance.
Older cached mesh records without units and complete source/CAD identities must
be regenerated. These checks precede all case writes and do not replace native
`checkMesh`, establish arbitrary tetrahedral non-overlap, or validate CAD physics.

The independently derived source conversion is
`V_mm3 = sum(det(b-a, c-a, d-a) / 6)`, `V_m3 = 1e-9 * V_mm3`, and
`q_W_m3 = requested_power_W / V_m3`. The integration invariant is therefore
`sum(q_W_m3 * cell_volume_m3) = requested_power_W`. Recomputed volumes control
normalization even when metadata differences are within roundoff tolerance.
The determinant threshold is 64 machine epsilons times the cube of the largest
cell coordinate difference; it rejects unresolved slivers instead of amplifying
their roundoff. Positive contributions are summed with compensated `math.fsum`.

Preparation retains `source-coupling.json` and returns `source_coupling`; execution
also returns this evidence with source IDs, mesh digest, SI region volumes and
requested/integrated watts. It explicitly labels solver convergence and heat/flow
balance `not_evaluated`. A failed native status stays failed. Source integration
conservation alone cannot establish a completed, converged or validated CHT solve.

Reproduce the original analytical checks with:

```powershell
python -m unittest tests.python.test_assembly_airflow tests.python.test_assembly_airflow_conservation -v
```

A 0.5 mm3 solid in a 1 mm3 enclosure is independently partitioned into 48,
384 and 3,072 tetrahedra. All three refinements retain 3.25 W (tolerance 1e-13 W)
and the expected 6.5e9 W/m3 source density. Malformed source/geometry/volume
records fail before writing a case. A mocked failed-to-converge engine result
tests status propagation only; it is not executed CFD evidence. The fixtures and
derivation are original SPIKE work with no external mesh, source or reference
data. Native airflow temperature, flow/heat balance and mesh/time convergence
acceptance remain pending as described above.

### Actual bounded native CHT execution, October 18, 2026

The previously unavailable WSL OpenFOAM runtime responded during this check:
Ubuntu `/usr/bin/openfoam2606`, version 2606. An original 48-tetrahedron case
passed the new source admission and native `checkMesh -allRegions`, then executed
through the existing hash-verified runner with a 60-second per-command budget.
Full inputs, commands, stdout/stderr, fields and observation hashes are retained
locally in `.local/validation/cht-source-admission-20261018/`; `run_case.py` and
`summarize.py` describe the exact generation and observation procedure.

The 1 mm cube has equal solid and fluid half-volumes, a 0.001 W solid load,
298.15 K exterior temperature and zero gravity. Both reference materials have
density 1 kg/m3, heat capacity 1 J/(kg K) and conductivity 1 W/(m K); fluid
dynamic viscosity is 0.01 Pa s. These deliberately simple reference properties
do not represent physical air or a PCB. Twenty 0.001-second steps with ten outer
correctors per step completed in static mode. Imported solid temperatures were
298.1778323..298.2239153 K, fluid cell temperatures 298.1520907..298.1729697 K,
velocity exactly zero and pressure 101325 Pa. Final thermal equation residuals
were 3.5292e-9 (fluid) and 7.5135e-9 (solid); the last two written temperature
fields agreed at the exported precision.

Negating the native inward-positive exterior `wallHeatFlux` integrals gives
0.00013768089959 W from the fluid and 0.00086231909443 W from the solid. Their
sum differs from the prescribed 0.001 W by 5.98e-9 relative. This is an observed
final power balance and iterative residual check on one grid and time step;
it does not qualify continuum temperature accuracy or mesh/time convergence.

The same mesh with a prescribed 5e-9 m3/s inlet on y=0 and pressure outlet on
y=1 **failed**. The maximum Courant number grew to about 100.6; at t=0.002 s
the engine aborted with return code 134 and negative temperature. The adapter
returned `failed` with empty imported fields, and all failure logs remain in
the separate `forced` directory. This failed case provides no accepted fields.

One revised case in `forced-small-step` used 1e-9 m3/s (mean prescribed inlet
velocity 0.002 m/s) and a 1e-8 s step for 100 steps. The minimum tetrahedron
inradius is 1.03553e-4 m: the input convective scale U*dt/h is 1.93137e-7 and
viscous scale nu*dt/h^2 is 0.00932548. The actual maximum logged Courant number
was 1.55491e-7. This case completed with native solid temperatures
298.1779424..298.2256488 K, fluid temperatures 298.1522221..298.1799947 K and
maximum returned fluid speed 0.0026061383 m/s. Final outward mass fluxes were
-1.00000000000000006e-9 kg/s at the inlet and 1.00000000024811330e-9 kg/s
at the outlet (relative imbalance 2.48113e-10). This establishes actual
moving-fluid and temperature execution for this tiny reference case. Its
startup energy storage and full open-boundary heat transport were not balanced;
no energy-conservation, continuum-accuracy or convergence claim is made.
General forced/natural-flow stability and refinement, physical-air properties,
general CAD and hardware correlation remain pending.
Knowledgeable numerical review remains required before release.
