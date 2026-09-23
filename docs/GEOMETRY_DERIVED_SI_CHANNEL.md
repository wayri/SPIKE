# Bounded Geometry-Derived SI Channels

## Status

SPIKE has executable **experimental** geometry-to-channel paths for either one
straight constant-width planar trace, one strictly bounded pair of straight
parallel coextensive traces, or an explicit `piecewise_planar` approximation of
connected constant-width, same-layer planar segments above one declared
reference zone. They are useful for inspecting narrow quasi-TEM models and for
closing analytical regressions. They are not a general PCB SI extractor,
production/signoff models, or protocol-compliance evidence.

The public contracts are:

- request: `spike/si-uniform-channel-request/v1`;
- result: `spike/si-channel-result/v1`;
- worker method: `run_si_uniform_channel`;
- CLI command: `spike si-geometry-channel <design.json> <request.json>`.

Supplying `victim_net` selects the paired path. `differential_mate_net` selects
the P/N mixed-mode result path. `victim_path_id` can disambiguate that path, and
`cross_section_vertical_cells` selects the bounded 2-D reference grid from 12
through 96 cells across the reference spacing.

The result always declares `model_status: experimental`,
`production_qualified: false`, and `compliance_status: not_evaluated`.

## Admitted geometry

The single-line extractor accepts a DesignIR v2 path only when all of these
conditions are explicitly satisfied:

- one unbranched, collinear, open chain of canonical tracks;
- one signal layer and one constant track width;
- positive trace thickness and conductor conductivity;
- one distinct canonical copper reference layer;
- an explicit reference net with exactly one simple polygonal zone without
  holes on that layer;
- one homogeneous dielectric permittivity between signal and reference; and
- positive signal/reference spacing; and
- complete projected trace-footprint coverage by the reference-zone polygon.

Arcs, vias, branches, layer changes, width changes, ambiguous paths, multiple
dielectric permittivities, missing reference zones, and incomplete material data
fail closed. In the strict default, bends also fail closed. In the opt-in
`piecewise_planar` mode, connected bends are admitted only when every segment is
on one layer, has one width, and forms one unbranched chain; segment and bend
evidence are retained. The solver cascades/averages its uniform sections and
does not model bend discontinuity, corner capacitance, or bend radiation. A
declared reference zone is required, but its full coverage proof is limited to
the projected copper footprint; it does not prove the return-current density or
the absence of a relevant discontinuity outside that footprint.

The paired path adds these strict requirements:

- exactly two distinct signal/victim nets;
- one straight, unbranched, constant-width path per net;
- both paths on the same signal layer, parallel, exactly coextensive, and free
  of longitudinal skew;
- a positive edge-to-edge gap with no touching or overlapping copper; and
- full projected coverage of both trace footprints by the same admitted
  reference-zone polygon.

The two widths may differ, but no third conductor, partial overlap, fanout,
arc, via, layer transition, plane hole, or reference-zone union is admitted.
The opt-in piecewise pair additionally requires matched parallel segments,
explicit skew and separation tolerances, and uses the minimum admitted segment
separation as a conservative cross-section. It records that approximation;
bend coupling and discontinuity physics are omitted.

## Numerical path

For one trace, the extractor computes a scalar per-unit-length model for the
admitted uniform cross-section. Capacitance uses the existing bounded
Hammerstad/Jensen planar estimate; propagation velocity determines inductance;
conductor resistance is the DC rectangular-section value; and dielectric shunt
loss uses the declared loss tangent. The uniform telegrapher-equation solution
is converted to a reciprocal two-port S sweep with one real positive reference
impedance.

For the pair, an independently written sparse finite-difference 2-D
cross-section solve produces the vacuum Maxwell capacitance matrix at three
bounded refinement levels. The dielectric matrix is the homogeneous relative
permittivity times that vacuum matrix. The quasi-TEM inductance matrix is
derived from the inverse vacuum matrix and the vacuum speed of light; resistance
is diagonal DC rectangular-section resistance; dielectric shunt loss uses the
declared loss tangent. The multiconductor telegrapher state transition produces
a four-port S sweep with equal real positive reference impedances.

The pair's cross-section boundary policy grounds the bottom reference boundary,
sets the two conductor segments on the top boundary, and uses finite natural
outer boundaries. The result records grid dimensions and inter-level matrix
change. Finite truncation and a recorded refinement sequence are not yet an
accepted field-convergence proof.

The requested frequency grid must:

- contain 3 through 32,769 points;
- start with an explicit DC sample;
- be finite, strictly increasing, and uniformly spaced.

SPIKE constructs real TDR and TDT results from an explicit Hermitian spectrum.
The first slice uses no window, padding, resampling, extrapolated DC, delay
removal, gating, or de-embedding. TDR impedance uses the requested real
reference impedance. These processing choices are recorded in the result and
are not silently substituted.

The paired port order is fixed and reported as `aggressor.near`,
`victim.near`, `aggressor.far`, `victim.far`. Its through TDR/TDT and optional
eye use `aggressor.near` to `aggressor.far`. The experimental crosstalk report
defines NEXT as `S(victim.near, aggressor.near)` and FEXT as
`S(victim.far, aggressor.near)` and reports magnitude, transfer dB, and the
worst sampled frequency. These are geometry-derived values inside this bounded
model, not validated general-PCB NEXT/FEXT or compliance limits.

When `differential_mate_net` declares the pair as P/N, SPIKE applies an
orthonormal near/far differential/common transform, derives an experimental
differential two-port, and reports its TDR/TDT plus the normalized deterministic
NRZ eye. This is not proof of common-mode balance, mode conversion, a real
transmitter/receiver, or a DDR/SerDes compliance condition.

When a bit rate is supplied, SPIKE can also convolve a deterministic PRBS7
sequence with the channel impulse response and emit a normalized ideal-source
NRZ eye. It requires at least eight time samples per unit interval and a
represented bit rate within one percent of the request. The reported BER value
is only a deterministic-ISI Gaussian proxy. It has no stochastic-noise,
rare-event, IBIS, equalizer, clock-recovery, package, transmitter, or receiver
qualification meaning.

## Current evidence

The focused regression corpus currently establishes only bounded software and
analytical behavior:

- one admitted DesignIR fixture reaches RLGC, two-port S, TDR/TDT, and the
  normalized NRZ result while preserving all experimental labels;
- a matched lossless analytical line has zero reflection, unit transmission
  magnitude, expected phase delay, and a flat reference-impedance TDR;
- the normalized eye is deterministic for a fixed request;
- strict-mode bent and via-bearing paths fail closed, while admitted
  `piecewise_planar` bends retain evidence and use the documented
  no-discontinuity approximation;
- the admitted pair produces a passive-sign Maxwell capacitance matrix, a
  four-port network with the documented order, and finite NEXT/FEXT traces;
- paired paths with unadmitted longitudinal skew fail closed, while the opt-in
  piecewise mode requires its explicit skew/separation bounds and cancellation
  interrupts the sparse cross-section solve;
- missing DC and nonuniform frequency grids fail closed; and
- the request/result schemas, worker method, CLI, and provenance digest agree.

This evidence does not validate the pair's field accuracy, general coupled
geometry, arbitrary-board extraction, frequency-dependent loss, return-path
discontinuities, or real hardware.

Both paths report numerical resource admission and support cooperative
cancellation. The current hard bounds include 32,769 frequency points, 8,192
eye bits, 1,048,576 eye waveform samples, and—on the pair—96 vertical and 1,024
horizontal cross-section cells. Admission prevents unbounded work; it is not a
physics qualification.

## Promotion ladder

The capability must remain experimental until every applicable stage below has
traceable evidence:

1. Extend projected reference-plane coverage evidence with reference-current
   continuity and field-sensitive return-path checks.
2. Add convergence studies for geometry discretization, frequency spacing,
   bandwidth, and time-domain reconstruction policy.
3. Validate frequency-dependent conductor loss, proximity effect, roughness,
   dielectric dispersion, and causal/passive behavior.
4. Validate the bounded matrix RLGC path against independently calculated
   even/odd modes and closed-form symmetric fixtures; define and pass numerical
   acceptance thresholds for all recorded cross-section refinement levels.
5. Validate vias, bends and bend discontinuities, launches, connectors,
   antipads, plane voids, and mode conversion before admitting those physics as
   anything beyond the recorded piecewise approximation.
6. Compare RLGC matrices, four-port S, NEXT/FEXT, impedance, delay, TDR, and TDT
   against an independent 2-D/3-D solver with identical materials, ports, and
   reference planes.
7. Correlate against measured two-port and four-port VNA/TDR coupons,
   preserving calibration, de-embedding, raw data, uncertainty, material
   tolerance, and fixture hashes.
8. Cross-check deterministic eyes against direct transient simulation, then
   validate statistical eyes, jitter/noise decomposition, bathtub curves, and
   BER confidence separately.

Agreement with another numerical engine is regression evidence, not a
substitute for measured correlation. Very low BER must remain labelled as an
extrapolation unless the method and confidence support the stated probability.
The paired Python implementation is a bounded reference solver; promotion also
requires the intended isolated packaged SPIKES implementation and verified
source/package numerical parity.

## Clean-room references

The implementation is SPIKE-owned and independently written. Published work is
used for equations, terminology, and validation design; third-party
implementation code, tests, wording, artwork, and proprietary limit tables are
not copied.

Primary and official references:

- NASA multiconductor telegrapher-equation report:
  https://ntrs.nasa.gov/api/citations/19900004089/downloads/19900004089.pdf
- NIST lossy multiconductor-line and RLGC measurement overview:
  https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=7607
- Barth and Iyer, modal multiconductor-line properties:
  https://arxiv.org/abs/1702.01771
- IBIS Open Forum current specifications index (IBIS 8.0 and Touchstone 2.1):
  https://www.ibis.org/specs/
- Kurokawa, power-wave definitions and scattering matrices:
  https://doi.org/10.1109/TMTT.1965.1125964
- NIST guidance on wave definitions and network-parameter conversion:
  https://www.nist.gov/publications/comments-conversions-between-s-z-y-h-abcd-and-t-parameters-which-are-valid-complex
- IEEE 370-2020 interconnect measurement and fixture practice:
  https://standards.ieee.org/ieee/370/6165/
- NIST eye-diagram de-embedding study:
  https://www.nist.gov/publications/statistical-study-de-embedding-applied-eye-diagram-analysis
- IBIS 8.0 jitter, noise, and AMI definitions:
  https://ibis.org/ver8.0/ver8_0.pdf

Standards and papers remain copyrighted. SPIKE links to them and records
provenance; it does not redistribute restricted materials. The official IEEE
370 reference code is BSD-3-Clause, but this clean-room path treats independent
fixtures and observable outputs as comparison oracles rather than copying that
implementation.

## Protocol and signoff boundary

Protocol suites may select this experimental stage only as a user-visible
engineering precheck. They do not supply normative masks, limits, fixtures,
source/receiver models, or certification procedures. SPIKE must not emit a
DDR, PCIe, USB, DisplayPort, HDMI, Ethernet, MIPI, or other protocol PASS from
this result.

A future protocol assessment must bind the authorized standard revision and
clause, device role, lane rate, encoding, reference planes, stimulus, fixture,
measurement bandwidth, clock recovery/equalization, uncertainty, limit, and
complete evidence bundle. Formal certification remains the responsibility of
the applicable standards organization or authorized test program.
