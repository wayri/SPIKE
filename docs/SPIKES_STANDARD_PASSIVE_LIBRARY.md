<!-- SPDX-License-Identifier: Apache-2.0 -->
# Configurable standard R/L/C library

The Studio catalog adds 2908 original configurable templates, not 2908
manufacturer SKUs. Open Component catalog, search `id:standard.`, and
double-click a template. Values remain editable; select an inch package code,
construction label, tolerance, and optional nearest preferred value. The
Parasitics & temperature tab holds explicit coefficients; Pins & connections
is separate from value entry. Unsupported terminal/model controls are disabled.

| Family | Included preferred-value range | Series |
| --- | --- | --- |
| Resistors | 1 milliohm to 1 gigaohm | E192 (2305 values) |
| Capacitors | 1 picofarad to 1 farad | E24 (289 values) |
| Inductors | 1 nanohenry to 10 henries | E24 (241 values) |
| Kelvin shunts | 1 milliohm to 1 ohm | E24 (73 values) |

Preferred-value tools support E3/E6/E12/E24/E48/E96/E192, arbitrary custom
nominals, and nearest-value recommendations with the percentage change shown.
Recommendations never claim stock, manufacturability or an exact manufacturer's
product. The range limits are mathematical editing limits, not ratings.

Package labels include inch 01005, 0201, 0402, 0603, 0805, 1206, 1210,
1808, 1812, 1825, 2010, 2220, 2512 and Custom/nonstandard. Inch 01005
must not be confused with a metric size code. A selected package does not
create geometry or infer ESR, ESL, capacitance, power or voltage capability.
Construction choices cover thin/thick/metal film, wirewound, shunts, common
capacitor dielectrics and inductor core/construction labels. Changing the label
alone does not change equations. Available values/packages/tolerances vary
with the actual manufacturer's family and suffix.

Tolerance inputs include 0.05%, 0.1%, 0.25%, 0.5%, 1%, 2%, 5% and 10%
and other explicitly entered values below 100%. Corner -1/0/+1 selects a
deterministic static adjustment; it is not a probability distribution.
Temperature coefficients are explicit 1/K and 1/K^2, not guessed ppm values.
For example 50 ppm/K is entered as `50u` in the linear-TC field.

RLC models compile explicit series R/L, primary R/C/L, external parallel C
and optional leakage R. Zero parasitics are omitted; leakage zero means absent,
not a physical short. Kelvin templates expose FP/FN/SP/SN, with body resistance
and independently represented force-contact branches. Zero contacts are exact
zero-volt branches, not guessed small resistors. Use distinct force/sense net
identifiers: native parsing rejects branches whose endpoints are already the
same node. Kelvin RLC extensions are unsupported rather than silently ignored.

The generated native subcircuit retains its internal primitives in the current
canvas, not a newly qualified manufacturer four-pin symbol. The compiler uses
static model temperature/corner; runtime `.temp`, self-heating, nonlinear core
saturation and bias curves do not automatically modify these coefficients.
See [original equations/tests](SPIKES_PASSIVE_MODEL_EQUATIONS.md).

Inserted model snapshots retain package/construction, parameters and compiled
recipe hash in document metadata; save/reopen and undo preserve them. These
snapshots are records of insertion, not live qualification if source is edited.
Library exports include the templates. The legacy `catalog()` API still returns
the original 5000 presets; `catalog(include_passives=True)` returns all 7908.
No compiled code is executed when importing these data-only libraries.

For a separate importable data-only package, run
`python scripts/export_spikes_standard_passives.py --output standard-passives.spklib`.
The exporter refuses to replace an existing file. Store/package import retains
the original per-record limitations and never downloads or executes vendor code.

The manufacturer browser also adds 18 selected exact MPNs, with source/rating/
tolerance/package evidence, including four Coilcraft/Pulse inductors. Resistors,
capacitors and inductors can be placed as explicitly ideal nominal models;
their sourced parasitics and ratings are not silently enabled. Isabellenhuette
four-terminal entries remain review-only; a generic Kelvin template does not
establish their measured accuracy or thermal behavior. Stackpole family sources
were located but exact records remain unresolved; no ordering-code combinations
were fabricated. [Manufacturer evidence and gaps](SPIKES_PASSIVE_MANUFACTURER_SOURCES.md).

Preferred-number facts were checked against official Vishay
[E-series](https://www.vishay.com/docs/28372/e-series.pdf) and
[standard ohmic values](https://www.vishay.com/doc/?52022=), accessed 2026-10-12.
E48/E96/E192 are independently generated logarithmic three-significant-digit
tables, retaining the standardized 920 exception. No vendor model/source code
or document artwork is redistributed. Package-specific impedance curves,
dielectric DC bias, precision drift/noise, saturation, aging, skin effect and
temperature/thermal qualification require applicable manufacturer data and
separate model-specific tests. Numerical human review is required before release.

## Verification checkpoint

The 2026-10-12 Studio run passed 420 of 421 tests; one host-restricted symlink
test was skipped. All 2908 preferred templates executed in the owned C++ DC
solver against independent divider/open/short oracles. Twelve focused passive
model tests also passed, including Kelvin sense loading, transient refinement
and resonances. Native editor screenshots and checks are retained under
`artifacts/studio-passive-library-20261012`; the separate `.spklib` export was
loaded back successfully. One earlier full-suite worker startup timed out;
its failure is retained in `artifacts/studio-passive-library-worker-timeout-20261012.json`.
The same lifecycle test passed in isolation and the subsequent complete suite
passed without relaxing its timeout/assertions. This remains development
evidence, not a qualified release or an installed-app update.
