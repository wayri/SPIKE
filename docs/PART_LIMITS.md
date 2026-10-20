<!-- SPDX-License-Identifier: Apache-2.0 -->
# Part limits, stress and headroom

Open **Engineering review → Part limits & stress**. Configure a part check,
save the rule, then **Run review**. This uses the existing engineering-review
worker and saved project workspace; it does not start or modify a solver.

## Workflow

1. Find the board occurrence and part. Equal reference designators on different
   boards are different targets; retained occurrence and component IDs bind rules.
2. Name the pin, operating case or check. Choose voltage, current, temperature,
   power, mechanical stress or frequency, with the rule's common unit.
3. Enter a minimum, maximum or both. Blank means unset, not zero. Enter the
   reference for percentage calculations, such as zero current, nominal rail
   voltage or ambient temperature. A missing reference leaves percentages unknown.
4. Record the rating source and operating conditions. Datasheet absolute maximum,
   recommended operation, a derated budget and a custom requirement are different
   policies: describe the one you actually intend. SPIKE does not infer ratings.
5. Enter the observed scalar and its source: exact result/measurement ID, source
   revision, case, location/pins, peak versus RMS and time/corner coverage. Review
   its units and validity, then mark it reviewed. Changing the observed value or
   observation source clears the review checkbox.
6. Save, run review, inspect failures and coverage, then export the JSON evidence
   or CSV report. A saved report is a captured input snapshot, not a live claim
   about subsequently changed solver results. Refresh observations explicitly.

Rules and observations can be imported/exported as `spike/part-limits/v1` JSON.
Imports replace the rule set only after admission and exact target matching.
The [original example](../examples/part_limits/part-limits.json) contains synthetic
voltage, thermal and over-current observations; these are not manufacturer data.

## Percentage definition

These percentages are a declared allowance-utilization policy, independently
authored for this report. They are not reliability probabilities, lifetime
predictions, fatigue calculations, manufacturer qualification or a combined
multiphysics stress law.

Let `x` be the observation, `r` the reference, `L` an optional lower bound and `U`
an optional upper bound. Any supplied reference must be strictly inside the
declared window. The numeric limit check is inclusive: `L ≤ x ≤ U`, omitting an
unset side. It uses decimal comparisons before display rounding.

- Toward an upper bound (`x ≥ r`): `stress % = 100 × (x − r) / (U − r)`.
- Toward a lower bound (`x < r`): `stress % = 100 × (r − x) / (r − L)`.
- Away from the only declared bound: utilization is zero. The opposite direction
  remains unbounded; this does not establish a missing physical rating.
- `headroom % = 100 − stress %`. Exceedances retain utilization above 100 and
  negative headroom. At a bound, stress is 100%, headroom is 0%, and the inclusive
  comparison passes. Percentages display to six decimal places; rounding never
  determines pass/fail.

| Declared check | Observation | Stress | Headroom |
| --- | --- | --- | --- |
| 0 V reference, 5 V maximum | 4 V | 80% | 20% |
| 3.3 V reference, 3.0–3.6 V window | 3.15 V | 50% | 50% |
| 25 °C reference, 125 °C maximum | 100 °C | 75% | 25% |
| 0 A reference, 2 A maximum | 2.4 A | 120% | −20% |

Temperature ratios use differences from the explicit reference. Adding 273.15 to
the observation, reference and bounds leaves the ratios unchanged. The physical
unit basis is [NIST SP 811, Chapter 4, section 4.2.1](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-4-two-classes-si-units-and-si-prefixes),
reviewed 2026-10-21: Celsius and kelvin intervals have the same magnitude. Code
does not automatically convert units: every value in a rule must use the selected
unit. Below-absolute-zero temperatures are rejected. No external code or fixture
was copied; derivation, implementation and scalar test cases are SPIKE-authored.

## Status and coverage

Numeric comparisons are retained separately from evidence status. Missing
observations, limits, rating sources, observation sources or explicit observation
review produce **UNKNOWN**, even if the raw numeric comparison would pass.
Unpopulated parts are **NOT_APPLICABLE**. A reviewed failed rule gives the report
**FAIL**; missing evidence or fitted parts without rules give **INCOMPLETE**;
otherwise the declared checks give **PASS**. This does not prove that all relevant
quantities, cases, pins or failure modes have been specified.

The part summary uses the largest declared allowance utilization only when all
that part's rules have reviewed evidence and percentages. Unknown evidence keeps
its summary percentage unknown. It does not combine distinct physical stresses.

## Persistence, evidence and limits

The optional `analysis.engineering_review.part_limits` field preserves backward
compatibility with older `.spike` projects. Source-data changes invalidate the
active review. Changes to rules invalidate the report. Save-with-results retains
captured observations and report evidence; result-free export keeps limits but
removes observations, observation-source text and review assertions. Exported CSV
includes all rules, part summaries and unchecked parts; formula-like text is
escaped. The UI paginates report rows and bounds rule-list rendering.

Requests remain within the engineering-review 8 MiB bound, with at most 20,000
rules and 20,000 parts. Decimal inputs are finite, at most 18 significant digits
and adjusted exponent within ±30. Arbitrary result-to-part attribution, pin-load
distribution, peak extraction, SOA curves, uncertainty propagation, manufacturer
derating models and automatic analysis reruns are not supplied by this feature.

Implementation: `python/spike_core/part_limits.py`. Evidence: independent scalar
oracles, inclusive and over-limit boundaries, bipolar and lower-only windows,
Celsius/kelvin invariance, unknown coverage, DNP, decimal rounding and extreme
ratio checks in `tests/python/test_part_limits.py`; storage/export checks in
`app/scripts/test-part-limits.mjs`. Human review remains pending; an experimental
prerelease disclaimer does not establish engineering qualification.
