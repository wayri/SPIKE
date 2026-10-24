# Independent analysis-performance review — 2026-10-23

## Result and scope

No actionable findings remain in the final reviewed changes. This bounded
independent review covered:

- Request-local custom-pad simplicity-result caching.
- Private admission reuse in composed tetrahedral CFD/CHT execution.
- Repeated-design summaries and parsed-model reuse in multiboard preparation.
- The primitive/dictionary fast path in assembly duplicate-value comparison.

The reviewer made no production changes. Implementation owners corrected the
findings below. Only small synthetic checks and focused tests were executed;
there were no large-board or stress runs under the task's below-6-GiB
available-memory restriction. This is an optimization/admission review, not
new validation of the governing physics or production qualification.

## Findings resolved during review

### CFD reuse binding

1. **Late ticket creation.** The initial implementation created the retained
   mesh ticket after flow execution. A flow cancellation callback could change
   the raw mesh, after which the ticket bound the newly changed source digest
   to previously admitted arrays. The final implementation captures a private
   snapshot and its binding before admission callbacks and retains that ticket
   through the composed solve. The reviewer independently verified that a
   callback duplicating a cell vertex index during `solve_cfd_tetra_stokes`
   now blocks the energy stage with a stale-source issue and returns no fields.
   The attempted pre-fix end-to-end run raced an implementation edit and
   failed to import; no pre-fix runtime result is claimed for this finding.

2. **Change-and-restore during admission.** Before/after source hashes alone
   were insufficient. In a real 12-cell fixture, callback 1 translated every
   source vertex by +0.25 m in x and callback 2 restored the source. The raw
   source and its digest returned to their original values, but the admitted
   first vertex was `[0.25, 0, 0]` instead of `[0, 0, 0]`. Admission now reads
   only the private pre-callback snapshot. The same reproduction now yields
   arrays identical to the pristine source. Persistent source changes are
   still rejected before a ticket is returned or consumed.

3. **List/tuple digest collision.** JSON encoding made a cell-index list and
   tuple indistinguishable, although fresh mesh admission rejects the tuple.
   The reviewer observed fresh admission rejecting a changed tuple while
   reuse accepted it. The final encoding path requires plain JSON containers
   before snapshotting/hashing. Both tuple mutation before reuse and an
   initially supplied tuple now reject without normalization or repair.

4. **Unbounded preliminary traversal.** The first plain-JSON type walk had no
   cycle/depth/node limit and could loop before the JSON encoder's cycle
   detection. This was identified statically; the unbounded implementation
   was not run on a cycle. The final walk has 500,000-node and depth-32 limits,
   in addition to the 32-MiB serialized limit. A single self-referential list
   was tested only after the bound existed and rejected promptly.

5. **Snapshot changed reduction order.** Decoding sorted-key JSON reordered
   boundary patches. For an ordinary 100–1000 K boundary-temperature case,
   the reviewer observed `_temperature_lift` changing from
   `0x1.7c4f350532bebp+8` to `0x1.7c4f350532becp+8`. The final private snapshot
   and reuse digest preserve mapping insertion order. Public provenance
   canonicalization is unchanged. Thirty seeded temperature-lift cases now
   match direct admission bit-for-bit, and changing patch insertion order
   after admission invalidates the reuse ticket.

The resulting invariant is that reused arrays came from an isolated,
admitted, order-preserving source snapshot. A ticket is tied to the original
source object and its order-sensitive JSON representation; it is checked
after the cancellation callback before reuse. Standard independent Stokes
and energy calls still take their ordinary admission path.

### Multiboard parsed-design reuse

1. **Stale admission after a callback.** With two occurrences of one design,
   a callback changed the raw contract to `INVALID` after the first job.
   The reviewer observed both jobs completing with the cached parsed model,
   although fresh parsing rejected the changed contract.
2. **Parser-significant type collision.** A proposed JSON-digest fix still
   allowed a callback to replace a valid custom-pad polygon list with a tuple.
   The digest stayed equal, the cached batch completed both jobs, and fresh
   parsing rejected the polygon type. This was independently reproduced.

The final solution conservatively reuses parsed models only when no caller
cancellation callback is supplied and the source is a plain-JSON tree.
Callback-bearing requests and Python-only container payloads retain their
previous per-occurrence parsing. The bounded, cycle-safe eligibility walk is
an optimization decision, not a new rejection or normalization path.
The reviewer reran the tuple mutation case: the second occurrence now fails
admission and only the first runner executes. The invalid-contract regression
and a legitimate hydrated-tuple payload regression also pass.

3. **Returned summary aliasing (root follow-up).** The root reviewer found
   that spreading a cached summary into multiple occurrence records shared
   its `bounds_mm` and `dimensions_mm` lists. The former repeated scan created
   independent lists. Occurrence construction now deep-copies the small
   summary while retaining the single geometry scan. This reviewer inspected
   that change and reran the updated 12-occurrence test: the summary is still
   computed once, and mutating both lists in the first occurrence leaves the
   second unchanged. The focused test passed in 0.003 s.

Design summaries remain request-local and keyed by retained design identity.
Each board still receives its own occurrence ID, namespace, transform, issues,
and result entry; links remain resolved through the occurrence graph. There
is no caller callback in summary generation. The inspected SI consumer does
not assign into its parsed design; one actual small SI protocol suite left
the complete parsed model's canonical digest unchanged.

## Other preservation checks

The custom-pad cache stores only the pure simplicity result under the complete
normalized coordinate tuple. Every pad's metadata and every coordinate are
validated before lookup. Dictionary hash collisions still require full tuple
equality. Coordinates are finite and bounded before lookup; the predicate has
no division or sign-bit-dependent branch, so equal positive/negative zeros
cannot alter its Boolean comparisons. Sixteen signed-zero variants passed
both batched and fresh-call validation. Four nonfinite/out-of-range second
pads were rejected after a valid first pad had populated the cache. The
128-entry and 32,768-vertex retention limits do not bypass validation when
full. Three focused custom-pad cache tests passed.

The assembly equality fast path returns the same ordinary equality for exact
JSON primitive types as the prior fallback. Exact dictionaries retain key
equality and recursive value comparison; tuple/list and general-Mapping
handling remains in the original fallback. The dedicated equality regression
passed, including tuple and Mapping semantics.

## Executed verification

In addition to the independent reproductions described above, the reviewer
executed focused repository tests for:

- Three custom-pad cache admission/revalidation/cap cases.
- CFD nested mutation, during-flow mutation, private-snapshot change/restore,
  and tuple-rejection behavior. The final three-test snapshot/tuple/flow run
  passed in 0.082 s.
- Assembly primitive/tuple/Mapping equality; repeated-design summary identity;
  and repeated-design parse identity.
- Multiboard callback mutation and accepted Python-container behavior. The
  final two-test run passed in 0.006 s.

A separate small 12-cell CHT pair compared complete fields and diagnostics
with duplicate admission forced versus reuse enabled. Only the energy
`elapsed_seconds` diagnostic was excluded. Both produced SHA-256:

`ea6279bdd94fd07f151037f6969ea5945f80cd6dc462ca5dd0b961383e02601d`

This pair used the repository benchmark's fingerprint helper to compare
outputs; it was not a timing series or an independent PDE reference solution.
No performance improvement is claimed from the reviewer's runs. Owners'
broader test suites and timings are separate evidence, not included in the
reviewer's executed-test counts.

## Reviewed source identities

SHA-256 values read after the final implementation changes:

| File under `python/spike_core/` | SHA-256 |
| --- | --- |
| `custom_pad_geometry.py` | `1cd09074a5074163d6d879b9e74e3570af3316d7943713287ad877b0e7a16ce3` |
| `assembly_designs.py` | `cb91f26584f62d5bf1a5bdd141bee4818441c154b56cdf64c6ca9a9f476026ef` |
| `cfd_tetra_mesh.py` | `0df731a2b4779b1db35c01cf0bcd6bb9f9212b78d9434abea1dfec928db954f1` |
| `cfd_tetra_cht.py` | `edcec801773e63d5fb16917c126ed53360497f31b9316d7257b393d91e375a1d` |
| `cfd_tetra_stokes.py` | `4d65d02bc73294407603e07de40f78b53108f96506a97992bfbaa9a5b0a556bc` |
| `cfd_tetra_energy.py` | `dfed313ebb53bd5bae7fbc262bd00628aeda14a5de81aa67f2457b333310e181` |
| `multiboard_analysis.py` | `14091ff8be67258f4ce7ccf8e22c7e43250bfa1dff94fe6d913de8229bf360e2` |
| `multiboard_execution.py` | `ca7af5f60a158db5b871af94866a82dcc2c058c9e2d2b916f8062329945fd38e` |

## Limits

The checks concern synchronous request-local execution and the reviewed
consumers. They do not establish thread safety against unsynchronized writes
from unrelated threads, whole-process peak memory, large-input capacity, or
all possible SI consumer paths. Callback-bearing multiboard requests do not
receive the parsed-model reuse speedup. No external numerical implementation,
comments, examples, or test data were read or adapted. Existing experimental
states and knowledgeable human review requirements before numerical release
remain applicable.

The summary-aliasing follow-up was not retimed. Existing component timings
isolate summary scanning and parsing and do not measure the newly added small
per-occurrence copy. They remain evidence for those measured components, not
a timing result for the final complete planner. Retiming was not required for
this bounded correctness review.
