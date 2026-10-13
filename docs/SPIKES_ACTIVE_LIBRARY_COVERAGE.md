<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKES active-library coverage

`standalone/spikes_project/studio/python/spikes_studio/active_library_coverage.py`
audits the installed exact-MPN catalog without turning discovery metadata,
generic presets, or helper circuits into model-coverage claims.

## Coverage contract

The audit reports 100 distinct **executable** manufacturer/MPN identities as
the minimum target for each of these overlapping engineering views: op amp,
BJT, NPN, PNP, MOSFET, NMOS, PMOS, GaN FET, SiC FET, MESFET, PIN diode,
diode, Schottky diode, controller, and PWM controller. For example, an
explicitly identified NPN counts in both NPN and BJT; it still represents one
manufacturer/MPN identity in each view.

Rows are deduplicated by case-insensitive `(manufacturer, exact MPN)`. Repeated
catalog rows, package presentations, parameter sweeps, generic component
families, equation benches, ideal helper circuits, and names without source
provenance do not inflate the count. Different orderable MPN strings remain
different identities; the audit does not guess that two manufacturer ordering
codes are electrically equivalent.

The three reported levels are intentionally separate:

- **Discovered** requires an exact manufacturer and MPN plus an HTTPS source,
  real access date, named document, and sourced-field inventory.
- **Executable** additionally requires a `spikes/active-model-evidence/v1`
  record with the model SHA-256 and a passed, dated, backend-named execution
  artifact bound by its own SHA-256.
- **Qualified** additionally requires passed, dated qualification evidence,
  its artifact SHA-256, stated scope, and named human reviewer. Qualification
  cannot outrun execution.

Fields such as `model.readiness`, `status`, a vendor name, catalog presence, or
a successful generic helper test are not execution evidence. Unknown,
optimistic, incomplete, or malformed evidence fails closed and is listed in
`issues`; it remains uncounted at the claimed level.

This is metadata admission, not artifact-file verification. The audit validates
the declared contracts, statuses, dates, references, and SHA-256 syntax; it does
not read the referenced artifact, recompute either digest, rerun a solver, or
assess the adequacy of the qualification itself. The workflow producing the
evidence must perform those checks, and release review must verify the referenced
files and hashes independently.

## 54/74 logic is exhaustive, not a numeric quota

"Full 54/74" has no invented finite target. The default report therefore uses
`target: null` and `status: unknown_universe`, even when individual HC packages
have been discovered. A completeness claim requires an externally sourced,
dated, explicitly enumerated `spikes/logic-54-74-manifest/v1` universe. The
audit compares identities against that manifest and reports missing and
unexpected discovery entries, missing executable entries, and missing qualified
entries. `status: complete` requires every expected identity to have admitted
execution evidence; merely discovering the whole manifest remains
`status: incomplete`. Qualification completeness is reported separately as
`qualification_status`. Functional Boolean APIs remain distinct from circuit
execution and manufacturer electrical qualification.

## Current bundled result and next gates

The bundled manufacturer catalog provides useful discovery coverage, including
op amps, BJTs, MOSFETs, and 20 SN54HC/SN74HC packages. At this checkpoint it
provides no digest-bound execution evidence for the active-device categories,
so all active executable and qualified counts remain zero. The 5,000 generic
component presets are intentionally excluded because they are not exact MPNs.

Closing coverage honestly requires, per exact MPN:

1. Acquire an applicable model and review its license and redistribution terms.
2. Preserve the model version and content hash; inventory dependencies.
3. Map model terminals to the exact orderable package and record applicability.
4. Pass parser and solver operating-point, AC, transient, limit, temperature,
   and failure-envelope checks with digest-bound artifacts.
5. Compare with suitable manufacturer/reference-engine or measured evidence,
   document exclusions and tolerances, and obtain knowledgeable human review.
6. For 54/74 completeness, acquire and maintain an authoritative enumerated
   family universe rather than declaring success at an arbitrary count.

Run the focused audit tests with:

```powershell
python -m unittest standalone/spikes_project/tests/python/test_active_library_coverage.py -v
```

The report is an inventory and evidence gate. It does not by itself validate
electrical accuracy, approve redistribution, or authorize release.
