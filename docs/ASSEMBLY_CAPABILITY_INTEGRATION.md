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
