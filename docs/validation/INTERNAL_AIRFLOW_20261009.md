<!-- SPDX-License-Identifier: Apache-2.0 -->
# Internal airflow integration evidence

Date: 2026-10-09. Experimental implementation; no production qualification.

The independently authored channel kernel passed analytical momentum/enthalpy,
semidiscrete exponential, axial/transverse refinement, conservation, cancellation
and malformed-input checks. Exact errors and equations are in
[the derivation](../INTERNAL_AIRFLOW.md). No independent established CFD solver
or measured hardware comparison has been completed for this new kernel.

The full Python suite passed 2,862 tests (22 skipped) during integration.
After final internal-airflow and time-audit changes, their ten focused tests
passed. A separate 25-test final focused run covered airflow, time refinement,
cooling comparisons and MCP. The final snapshot addition was subsequently
covered by the ten numerical tests and the UI admission regressions.
The frontend production build passed; final TypeScript compilation, parser,
button-standard, architecture and documentation checks passed.

The native development SPIKE window successfully sent an actual channel request
to its local worker; returned accessibility text reported 2.4 W wall heat and
2.4 W coolant enthalpy gain with 4.44e-15 W imbalance. Initial wide controls were
visually inspected. A separately generated original 50 W/m2 lower-wall fixture
imports actual computed fields and reports 0.24 W input with 4.72e-16 W imbalance.
It is retained in `app/scripts/fixtures/internal-airflow-result.json` for the
native acceptance entrypoint; it is not a mock field.

Final field and narrower native screenshots could not establish visual
acceptance: foreground user activity caused unrelated-window pixels to be
returned by the capture surface. The final UI therefore has automated rendering
and lifecycle checks, but no claimed final narrow native visual pass. The
verification window and development server were closed after testing.

The thermal scenario stores the channel request/result; the panel checks all
input values when reopening. A native save/reopen workflow has not been exercised
for this new scenario member. Snapshot identity checks are presentation admission,
not an independent numerical validation of untrusted reauthored results.

General geometry flow, turbulence fields, solid/fluid CHT, radiation exchange,
coolant blocks and automatic coupling to retained assembly solids remain outside
this channel model. See [the staged research work](../THERMAL_RESEARCH_ROADMAP.md).
