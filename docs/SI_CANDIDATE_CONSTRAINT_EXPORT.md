<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI01-S02 reviewed finite sampled constraint export

This bounded offline stage turns an existing SI01-S01 candidate-study result
and an explicit review decision into a neutral JSON manifest. It does not run a
solver, create a limit from observed extrema, change a board, or apply a native
layout rule. SI01 remains open for general topology, geometry-backed constraints,
native integration, physical validation and a family benchmark.

The caller supplies the complete `spike/si-candidate-study-result/v1` object and
a `spike/si-candidate-constraint-selection/v1` record containing the expected
canonical result SHA-256, candidate ID, `accept_sampled`, `hold`, or `reject`
decision, reviewer ID, review basis, and selected original limit IDs. The exporter
checks the source-request digest, recomputes finite sampled extrema and statuses
from retained child traces, and rejects altered bounds, witnesses or coverage.
An accepted manifest requires complete passing evidence for every selected limit.
Hold and reject records remain inspectable but have `applicable=false`.

The manifest retains all candidate statuses and the selected cases' status,
issue and request digest. It exports only the original supplied metric, frequency
band and bound plus recomputed witnesses and margin. Scope flags state that no
continuous-band, native-layout, physical, production or family qualification is
established.

Run the file adapter with two reviewed JSON inputs:

```powershell
python examples/si_candidate_constraints/run_export.py result.json selection.json --output manifest.json
```

Run the independent synthetic contract checks directly, or emit a fresh
source-bound receipt and log at new project paths:

```powershell
python -m unittest tests.python.test_si_candidate_constraints -v
python scripts/verify_si_candidate_constraints.py --output build/si01-s02.json --log build/si01-s02.log
```

The verifier hashes its implementation, documentation, adapter, tests and the
existing SI01-S01 implementation/schema sources whose result semantics it
derives from. Exact before/after maps must match. Its reusable receipt validator
requires the exact six-test inventory, rejects every nonempty unittest outcome,
binds the retained log path/digest/content and requires all qualification scope
flags to remain false. Adversarial validator tests are separate from the six
stage tests so the executed inventory cannot change while validating itself.
