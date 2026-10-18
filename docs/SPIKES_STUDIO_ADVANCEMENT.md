<!-- SPDX-License-Identifier: Apache-2.0 -->
# Studio advancement and evidence boundaries

This increment improves schematic editing, discovery and model-library access.
It retains the existing native numerical engine. It does not establish overall
parity or superiority over ngspice, LTspice, Qucs, Qucs-S, QSPICE or SIMPLIS.
Validated capability claims remain in [solver status](SOLVER_STATUS.md).

## Implemented workflow increment

- Selected-component copy/duplicate uses a placement preview, rotation,
  cancellation, repeated placement and an undo transaction per placement.
  Unsupported dependencies must be rejected explicitly rather than rebound.
  See [editing contracts and boundaries](../standalone/spikes_project/studio/docs/SCHEMATIC_EDITING.md) and its regression tests.
- The library browser exposes five established, configurable lumped-device
  builders, including explicit bulk/substrate and force/sense terminals.
  These are generic unqualified models, with the original builders' limits.
  See [library integration and provenance](../standalone/spikes_project/studio/docs/LUMPED_PHYSICS_LIBRARY.md).
- A per-palette discovery index retains normalized installed-library text and
  at most 16 result pages. Literal-match shortcuts are used only when their
  ordering is provably identical to the shared matcher. Other searches use
  the existing fuzzy ranking. Signals and current project collections remain
  live; the index does not cache a circuit or a solver result.
- Explicit V()/I()/P() signal completions remain reachable even when a large
  component catalog fills the general suggestion list.

`scripts/benchmark_spikes_discovery.py` compares complete result identities and
order before reporting timing. It measures search/model work, excluding drawing
and solver execution. Index construction, first-query and cached-query costs
must be distinguished. Timing evidence is machine-specific, not a competitor
performance result.

## Meaningful competitive targets

The following targets are development and evidence requirements, not checked
capabilities. Product feature pages establish comparison areas; they do not
establish relative accuracy or performance.

| Area | SPIKES acceptance evidence required |
| --- | --- |
| Schematic productivity | Reproducible build-edit-wire-probe-run tasks; keyboard-only and pointer workflows; undo/reopen correctness; measured input-to-frame latency at declared circuit sizes |
| Model coverage | Exact device family, pin order, parameters, supported analyses, provenance, redistribution terms and independent references; catalog rows alone do not count as qualified models |
| SPICE compatibility | Versioned syntax/analysis/device matrix; equivalent-model decks; malformed input, unsupported dialects and convergence failures retained |
| Switching power | Applicable switched-device models, periodic settling and stability evidence; compare identical models and operating conditions; averaged stability is a separate capability |
| RF and mixed signal | Appropriate RF analyses, port/noise semantics and event/analog timing; a time-domain RLC example is not nonlinear RF or mixed-signal qualification |
| Performance | Accuracy-first comparisons, cold/warm runs, memory, cancellation, thread scaling, declared hardware and independently reproducible medium/large circuits |

Existing tools are retained as references where supported:
`scripts/run_spikes_competitive_benchmarks.py` exercises a small shared subset;
`scripts/run_spikes_public_equal_model.py` and
`scripts/run_spikes_parity_checks.py` address additional declared scopes.
Their exact reports determine what passed. Missing engines, timeouts, skipped
cases and unsupported analyses are not wins. No comparison is published from
this local UI update.

## Primary product documentation reviewed

Reviewed on 2026-10-18 for capability context only. No external implementation,
models, circuits or artwork are incorporated by this increment.

- [ngspice features and extensions](https://ngspice.sourceforge.io/extras.html):
  model interfaces and co-simulation make device and integration coverage
  separate comparison areas.
- [Analog Devices simulation models](https://www.analog.com/en/resources/simulation-models.html):
  LTspice's manufacturer model library is a distinct coverage target.
- [Qucs technical documentation](https://qucs.sourceforge.net/tech/technical.html):
  RF and harmonic-balance work needs its own reference evidence.
- [Qucs-S backend documentation](https://qucs-s-help.readthedocs.io/en/latest/overview/choosing-a-sim-backend.html):
  the frontend and selected simulation backend have separate responsibilities.
- [Qorvo QSPICE product documentation](https://www.qorvo.com/design-hub/calculators-simulation/qspice):
  use versioned, measured workloads rather than general performance claims.
- [SIMPLIS overview](https://www.simplistechnologies.com/documentation/simplis/what_is_simplis/topics/what_is_simplis.htm)
  and [periodic operating point](https://www.simplistechnologies.com/documentation/simplis/simplis_reference/topics/simplis_pop_overview.htm):
  specialized switching-system and periodic analysis are separate method gates.

Future numerical changes still require independent derivations, primary method
references, applicable units/assumptions, executed verification and knowledgeable
human review under [numerical method evidence](NUMERICAL_METHOD_EVIDENCE.md).

## Local build and installation

Use the established isolated Studio freezer and Windows installer recipe.
Preserve the source manifest, dependency inventory, native-engine hash, frozen
smoke report, final artifact checksum and installed-payload comparison. The
local update remains an unsigned engineering preview. A local install does not
promote the full cross-platform release gates or qualify new physics.
