<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver source layout verification, 25 October 2026

This is software migration evidence, not new physics qualification. The
[layout manifest](../solvers/source-layout.json) records 405 Python module moves
and 70 native file moves. [ADR 0145](../adr/0145-solver-source-layout.md) records
the boundary and source-identity consequences.

## Changes and invariants

Implementation owners now live under `python/spike_core/solvers/<domain>/<subgroup>/`
and `src/solvers/<domain>/<subgroup>/`. Imports, native includes, CMake inputs,
source-relative resources, worker freezer names, standalone packaging and active
documentation references follow those locations. Internal imports remain package
relative so both existing package namespace spellings resolve consistently.
Contracts, fixed CLI/worker entry points and worker method IDs remain stable.

No equations, constitutive laws, numerical tolerances or compiler numerical flags
were intentionally changed. For all 405 moved Python modules the original bytes
were retained locally before editing. Comparing original and migrated ASTs in the
same interpreter, excluding import statements and reversing the recorded path and
source-location substitutions, initially found no other syntax differences. A later scan still matches 404 modules;
`native_cht_result.py` now contains a concurrent workstream's new momentum
validation call and diagnostic text. Those edits were preserved, and are not
claimed as part of this mechanical migration. AST dump formats
differ across Python versions; comparing digest strings produced by different
interpreters is not a valid equivalence check. The retained comparison uses
Python 3.12.9 on both sides. This check complements numerical regressions; it does
not prove every import has identical semantics or establish physical accuracy.

Native moves used mechanical path/include substitutions. Native working-tree
pre-move byte snapshots were unavailable, so no native hash-equivalence claim is
made against Git HEAD or other preexisting work. Fresh builds/tests provide the
executed native evidence below.

## Executed software evidence

| Check | Result |
| --- | --- |
| Representative pre-move numerical baseline | 86 tests passed in the provisioned project environment |
| Same initial numerical selection after moving | 86 tests passed |
| Expanded numerical/import checks | 144 tests passed |
| Worker, packaging, snapshot and layout integration selection | 45 tests passed |
| Publication/resource-packaging selection | 20 tests passed |
| Assistant/package namespace recovery | 26 tests passed in a fresh process with loopback access |
| Model-library fresh-process replay | 15 tests completed, one skipped, no failures |
| Native circuits/geometry | 8 CTests passed after compilation/linking |
| Exported circuit SDK | Fresh generated archive; all six C++ headers compiled and linked; required behavioral-expression header included |
| Native PEEC/SI | 2 CTests passed |
| Native airflow/CHT | 2 CTests passed; airflow required approximately 269 seconds |
| Rust host | 81 tests passed, one ignored |
| Frontend | Architecture/control checks, parser and all solver-suite/template checks passed |
| Layout and publication gates | Passed; 405 Python and 70 native destinations verified |
| Active retired-file reference scan | No retired moved-file references found outside intentional history/manifests |
| Documentation | 871 repository-relative README links resolved |

Windows sandbox restrictions initially blocked temporary files and loopback
sockets. Those checks were rerun with normal access; sandbox failures are not
reported as passing executions. Default global Python lacked `jsonschema`; the
provisioned `.venv` was used for numerical/integration verification.

## Isolated frozen worker

The retained migration candidate under `build/solver-reorg/frozen-worker-r3/` was built with
PyInstaller 6.21.0 using fresh isolated native inputs. Existing bundled workers,
installers and qualified native artifacts were preserved. Its eight runtime
qualification checks passed with matching source/packaged snapshot digests.
The interactive circuit probe includes its analytical RC and checkpoint checks.

Exact source coherence passed for 548 inspected frozen modules; all 265 schema
JSON files matched. The retained source snapshot is under
`build/solver-reorg/frozen-source-snapshot-r3/`. Worker SHA-256:
`b580655ac40ba096e7b2baded9a3975e566e73a28e9b264a0adbbbde44612ccd`.
After that check, concurrent work changed `service_em_cosimulation.py` and
`native_cht_result.py` and added required `native_cavity_momentum.py`. The latest
active-source coherence check therefore fails closed: two changed modules and
one newly required module absent from this worker. All 548 inspected code objects
still match their retained snapshot; current release policy additionally requires
the new module. The candidate is baseline evidence, not a current release.

This does not establish clean-machine installation, other OS builds or complete
native-source equivalence.

The first candidate passed runtime probes but became source-incoherent after
the namespace fix. It remains retained separately and is not the final candidate.

## Historical evidence and remaining scope

Source-bound receipts bind exact paths/bytes, not merely equations. They were
not rewritten to make the migration appear qualified. A comparison against
retained pre-move modules found 22 historical receipts already had source drift
before this migration; additional path/byte changes invalidate current-tree
replays until their campaigns are genuinely rerun and rebound. This is not
permission to waive those gates or reuse their prior promotion for new bytes.

The complete Python suite ran 5,552 tests in 4,910.630 seconds: six failures,
50 errors and 86 skips. Of the 56 failing events, 48 are historical source-bound
receipt gates; six captured the earlier namespace state and subsequently passed
in fresh focused replays. One backlog test captured an intermediate privacy
projection. One refinement setup failed before producing a report: its dynamic
source inventory still assembled retired flat paths. That inventory is corrected
and its existence regression passes. The fresh focused refinement replay passed
all 12 tests in 18.965 seconds, including three actual supervised levels and
adversarial evidence checks.
The full log and categorized inventory remain under `build/solver-reorg/`.
Focused passes do not establish a clean full-suite result.

## Unpublished research

New optics/photonics, particle and electron-optics code, tests and research
documents remain local/ignored. The publication gate rejects them in Git
HEAD/index (including forced additions), exported resource manifests and actual
worker candidate inputs. CI/release workflows run the gate. The explicitly
retained public Optycal RF extension is unaffected. Public roadmap projection
removes the private OP work while ignored backups preserve the original records.

No commit, push, remote history edit, installer publication or physics promotion
was performed as part of this migration.
