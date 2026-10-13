# Retained 3D thermal volumes: source acceptance

Date: 2026-10-06. Experimental source implementation; this is not a release or hardware qualification.

## Implemented evidence

- Retained board effective-layer prisms and duplicate board occurrence admission.
- Exact original closed STEP box: 24 mm³, model and occurrence transforms retained; multi-solid compound rejected.
- Original analytical combined convection/radiation slab and manufactured quadratic source refinement. RMS temperature errors decrease 48.45 → 12.88 → 3.273 K over the tested meshes.
- Positive-K bounded Newton, emissivity/range admission, failed convergence, exact triangle radiation moments/tangent and heat conservation checks.
- Owner-box overlap pruning keeps separated dense duplicate bodies from consuming the inter-occurrence comparison budget; intersecting bodies remain rejected.
- Legacy saved handoff migration checks original file/result integrity and physical/input digests before rebinding; temperature values remain unchanged.
- Manifest-bound project inventory and package-only, bounded SHA-verified artifact reads; generation preserves original project bytes.
- GUI generated-mesh admission, result invalidation after boundary changes, actual mesh/sample ownership and K/C mapping.

## Checks actually performed

- 46 focused Python solver, admission, persistence and project service tests passed in the project Python 3.12 environment.
- 14 real OCC runtime/meshing tests passed with the admitted installed Windows Python 3.11/Gmsh 4.15.2 runtime, including duplicate board volumes and original STEP solids.
- Additional final radiation, legacy and project persistence rerun: 18 passed.
- TypeScript noEmit, production frontend build (2,019 modules), field-study integration, thermal volume plotting, board parser and button standard checks passed.
- Architecture guard and changed documentation link/format checks passed.
- Rust host: 38 passed, one existing ignored test.

Repository-wide Python discovery completed: 2,741 tests in 535.993 s, initially one failure, four errors and 15 skips. The model-cache checks (two errors) and headless descendant cancellation (one failure) passed when rerun with normal access. Two release-verifier tests remain blocked by the absent historical `artifacts/releases/beta-0.3.0-beta.1-coherent/SPIKES-0.3.0-beta.1-release.json` fixture; no tests were weakened or skipped to conceal it. Full output is in `.local/thermal-full-python-check.log`. Native wide/narrow SPIKE screenshots and installed-payload acceptance were not performed for this source change.

## Scope limits

No automatic board-internal component promotion, inferred materials/contacts/powers, solved airflow, enclosure radiosity, general compound STEP, formed flex, curved board outlines or transient solid solve. Effective board layers homogenize patterned copper/via/drill detail. Decorative render meshes are never treated as physical solids. The reference steady solve remains bounded to 5,000 tetrahedra and 10,000 nodes. Meshing currently needs a separately admitted local development runtime; redistribution is not approved by these tests. Numerical changes require knowledgeable human review before release.
