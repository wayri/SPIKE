<!-- SPDX-License-Identifier: Apache-2.0 -->
# PI01-S02 annular source contacts and coupled barrels — 21 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

**Bounded increment verified; full PI01-S02 remains in progress.** Explicit
axisymmetric annular lands now support independent finite patches, authenticated
native circular-pad geometry and a fresh passive barrel/circuit solution.
Every unit-response and final field is retained. Actual barrel currents supply
signed vector density and separately owned gap losses; imposed ownership-helper
currents are never reused. The implementation remains an experimental offline
reference, with production and complete-board qualification false.

## Mathematics, provenance and acceptance

The [annular method](../DC_ANNULAR_LAND.md) records the independently derived
cylindrical RT0 basis, scalar SI conductivity, conservation, Ohmic mass,
quadrature analysis, analytic axial/radial references, harmonic fields and
independent finite-volume spreading oracle. The
[circuit method](../DC_ANNULAR_CIRCUIT.md) derives reduced port resistance,
explicit incidence KCL/KVL, body gauges and source work versus separate land,
barrel and resistor heat. [ADR0127](../adr/0127-explicit-annular-field-circuit-ports.md)
records boundaries, reference implementation choice and limitations.

Reviewed primary foundations are Haus and Melcher's MIT online *Electromagnetic
Fields and Energy*, sections7.2/7.4 (steady conduction, conservation, linear
superposition and uniqueness),7.5 Example7.5.2 (axial conductor/radial washer)
and5.7 (polar separation). Exact reviewed portions and equation-image limits are
in the two method documents. Native pad/drill assumptions were checked against
the official KiCad S-expression format, pad and drill definitions at
[the specification](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/),
reviewed2026-10-21. These are physical/format foundations, not certification of
the new discretization. Code, derivations, fixtures and oracles are original
SPIKE Apache-2.0 material; no external implementation/data or dependency was added.

Acceptance was frozen before implementation. Analytic full-annulus axial and
radial R and both harmonic field components are checked independently. Physical
Gauss integration verifies returned vector fields and volume loss. Spreading
requires reference-grid agreement below0.2%, improving three-level error and
finest error below2%. Explicit resistor-star ordinary nodal analysis independently
checks the reduced circuit. All-body KCL, per-edge KVL and source work use1e-8
physical operand scales; local field conservation/weak-law witnesses use1e-9.
No passivity projection, current correction or board threshold relaxation occurs.

## Executed verification

- [Source-bound receipt](parity/PI01-S02-annular-contact-20261021.json),
  log ([bundled original execution log](parity/PI01-S02-annular-contact-20261021.log)) and
  [raw response/final field report](parity/PI01-S02-annular-fields-20261021.json):
  **30 tests, zero skips,33 hashed source files unchanged before/after/current.**
  Seven annular, seven integration, four independent circuit, six source-admission
  and six adversarial retained-evidence tests pass. The gate revalidates the
  earlier rectangular/ownership receipt and its finite-contact dependency;
  historical results and source hashes were not patched.
- **47 existing DC/Marble regressions pass**, zero skips: copper-domain,
  conservative density, conforming DC, iterative RT0, Marble probe and refinement
  audit. An initial invocation mistyped the copper-domain module name; that
  invocation failed import, then the corrected complete47-test invocation passed.
- Supplied and source-authenticated CLI runs both exit0. Their saved actual
  fields pass independent retained-result admission; overwrite is rejected.
  Local artifacts are under `build/pi01-annular-20261021/`.
- Independent numerical/adversarial review found two P2 gaps: nonzero current
  could underflow to zero circuit/retained heat, and an authenticated zero-drive
  source run could substitute for the acceptance fixture. Both were repaired
  and original counterexamples independently rerun. Residual normalization,
  positive dissipative-work checks and exact fixture identity now reject them.
  Forged response columns/extreme traces, barrel density/volume/heat, contact
  identity and gauges also reject. No blocking finding remains in this scope.

The first combined tracking invocation ran 19 checks and failed three backlog
checks because previously Done SI receipts were stale against shared changes to
`schemas/manifest.json` and `docs/RLGC_LINE_JUNCTION.md`. This increment did not
edit either input. Nine original gates were then actually reexecuted: SI02-S06,
SI01-S01 and SI02-S07 through SI02-S13, with **122 test executions and zero
failures/errors/skips**. Every new receipt/log was revalidated against current
sources after all runs finished. Their fresh `*-annular-replay-20261021.json`
and matching logs live beside the annular receipt. The ledger points to these
new runs and preserves the original receipts in verification history; no
historical hash or result was patched, and no stage status was promoted.
The corrected final combined tracking/evidence invocation passes all **19
checks with zero skips**. Architecture, scoped whitespace and the generated
reference-inventory check also pass. Full-suite testing was not performed.

Runtime: Python3.11, NumPy2.2.6, SciPy1.17.1. Field quadrature16 points is checked
at32 points; retained witnesses independently integrate physical basis fields
at32 points. This comparison is numerical evidence, not a rigorous quadrature
error certificate. Cancellation is between bounded solves; factorization
fill/time remains supervised offline. Model/resource/condition limits are in
the method documents. There is no universal tiny-current accuracy guarantee.

| Spreading mesh | Resistance error versus independent FV128x64 |
| --- | ---: |
| 4x2 cells | 5.430129% |
| 8x4 cells | 1.764103% |
| 16x8 cells | 0.515183% |

The independent reference is8.131586982855074e-6 ohm; FV64x32 versus128x64 differs
by0.1242%. The three-land uniform reference includes0.3mm total land thickness
and1.8mm total gap, giving1.4184631532858586e-3 W at1A. The source-authenticated
two-land circular-pad example dissipates3.3104263741926335e-4 W at1A, with
explicit electrode bands, supplied slab geometry and material. These are
synthetic bounded predictions, not manufactured-board measurements.

## Source and remaining stage conditions

The minimal original KiCad fixture has one circular plated pad with a centered
0.3mm drill and0.8mm land at(10,20)mm. Importer-owned native proof cross-checks
exact UUID, dimensions, layers and net; rejects offsets, NPTH/noncircular pads,
ambiguous UUIDs, unsupported padstacks/layer-removal and unknown drill grammar.
It pins source hash and reimports before/after an authenticated solve. Slab faces,
conductivity, barrel plating thickness and finite electrode bands remain supplied
model inputs. Native KiCad CLI fixture checking could not complete because its
HKCU initialization was denied in this environment; importer/solver tests passed.

A separate actual EBrake geometry-only probe authenticated circular pad
`bddbf31b-816c-466b-abca-f8bde64e55f4`, net`/BOUT2`, center(80.49,80.97)mm,
bore radius0.65mm and outer radius1.4mm against the existing board SHA256
`d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca`.
Its local binding is `build/pi01-annular-20261021/ebrake-source-binding.json`.
This selected-pad audit neither chooses the original study electrode nor solves
surrounding board copper. Original EBrake load support remains undefined/outside
planar copper, and no new EBrake or Marble field/convergence acceptance is claimed.

Uniform full-azimuth Neumann patches use conjugate mean potentials; pointwise
interface continuity/equipotential metal, angular crowding, general polygonal
contacts and arbitrary source-backed board assembly remain unresolved. Full-board
unique-volume vector-density statistics and original EBrake/Marble DC/AC/SI gates
remain required. Thermal transfer/material feedback, full-suite, installed
package, hardware measurement and knowledgeable human numerical release review
are separate unexecuted qualification gates. Coordinate with the existing
“Build modern SPIKE solver suite” chat; its CFD/propulsion edits were preserved.
