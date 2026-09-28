<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# PEEC numerical safety and consumer policy

These are executable regression requirements, not claims that the legacy
line-filament model has become a qualified volume extractor. The physical
Marble/MODULAR defect remains tracked in
[the volume correction record](PEEC_VOLUME_CORRECTION_20260924.md).

## Invariants learned from the failure

1. Self and mutual entries must represent the same finite current basis.
   Positive diagonal entries, a small solve residual, or even a positive matrix
   cannot prove correct geometry. Via circumference is an equivalent resistive
   width, not its magnetic cross-section. Overlapping bases require consistent
   resistance as well as inductance; duplicating copper is not mesh refinement.
2. Do not repair physical energy by PSD projection, diagonal inflation or
   tolerance relaxation. Both AC and transient reject negative-energy modes.
   Retain zero-energy topology modes. Singular line samples must not be skipped;
   the legacy kernel now rejects them after OpenMP workers join.
3. Admission must reject nonfinite geometry/constants/frequency, impossible
   dimensions and ignored configuration options. Strict floating point is
   required for the PEEC kernel so finite-value guards remain meaningful.
4. The old native `solve_frequency` entry point is unsupported: it conflated
   filament and node indices. Use the topology-aware branch-incidence solver.
   MNA requires finite compatible arrays, a unique solve and a checked residual.
5. The approximate capacitance kernel must reject an indefinite potential
   matrix and failed residuals. Never apply an inductance threshold to farad
   entries; this previously erased valid self capacitance.
6. A failed or error-bearing extraction is not a circuit model. SPICE import
   rejects it. Reviewed network indices and mesh endpoint identities must be
   exact; permissive integer coercion and missing provenance cannot remap ports.
   Negative/nonfinite reviewed passive R/L/C values are errors, not zero clamps.
7. Any extraction error invalidates the parent result, even if another port
   succeeded. Failed-result provenance retains bounded H-valued passivity
   metrics, `solved=false`, and `failure_stage=physical_inductance_admission`.
   Never treat these diagnostics as solved fields or impedances. Consumers must
   suppress partial data from failed/blocked/unsolved results while showing the
   original diagnostics.
8. Source changes are not deployed binary changes. Rebuild for the consumer's
   Python ABI, verify hashes and regression outcomes, and refresh staging through
   the package workflow. Do not overwrite signed/pinned artifacts or invent
   qualification when packaging, board convergence or human review fails.

## Permanent coverage

- `tests/test_peec_admission.cpp`: native malformed inputs, ignored options,
  singular interactions, capacitance passivity/retention and unsupported stub.
- `tests/test_volume_inductance.cpp`: independent finite-volume references and
  refinement; this tests a standalone prototype, not the production extractor.
- `tests/python/test_peec_energy_admission.py`: failure evidence, no usable
  results from failed extraction, MNA nonfinite/rank/residual checks and parent
  propagation of loop errors.
- `tests/python/test_transient_peec.py`: no projection, native negative modes
  rejected without waveform, valid zero modes preserved.
- `tests/python/test_peec_spice_export.py`, `test_peec_field_provider.py`, and
  `test_loop_parasitics.py`: downstream admission and reviewed identity.
- `app/scripts/test-trace-result-plots.mjs`: suppression of failed-result plots.

## Local rollout record, 2026-09-24

The corrected CPython 3.11 and 3.12 extensions are rebuilt locally. Previous
binaries are retained under `build/peec-audit-20260924/` for investigation and
rollback; they are not recommended fallbacks for rejected geometry. Nine native
admission groups pass in both build configurations; the rebuilt CPython 3.12
environment passes 41 focused Python tests. Architecture and trace plot tests
pass. This is not a Linux, installed-machine or public-release qualification.

The default Python 3.11 suite completed 1,836 tests in 305.280 seconds with
two skips and no failures. That run used the first safety rebuild; final
additional native range guards were checked by nine native groups on both
ABIs, the 41-test Python 3.12 run, and a 35-test focused Python 3.11 rerun
after refreshing its extension. Optional real-board failures are not covered
by the default-suite pass. Logs and source/binary hashes are retained in
`build/peec-audit-20260924/`; none of these results qualifies the unfinished
finite-volume integration.

All five owner-approved consumer tasks received the safety notice. The actual
PI candidate owner, **Continue PI open source release**, is coordinating
PI-only adoption; withheld SPICE/transient modules must not leak into that
candidate. The visualization owner is preparing fresh isolated package staging.
Notifications and staging are not proof that every installed copy is updated.
No Git remote push or public publication is part of this rollout.
