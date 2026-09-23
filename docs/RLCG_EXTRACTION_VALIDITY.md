# RLCG Extraction Validity

## Current contract

`spike.peec_2_5d` version 0.4 emits `spike/rlgc-network/v1` driving-point
networks. With explicit terminals and `options.pdn_candidate_ports`, it also
emits bounded `spike/pdn-multiport/v1` shared-reference Z matrices for PDN
candidate screening. The parameters do not all have the same validation
status:

| Parameter | Current model | Reported status |
| --- | --- | --- |
| R(f) | Geometry DC resistance plus isolated-slab skin effect; optional Hammerstad RMS roughness | Extracted, approximate |
| L | Full mutual partial-inductance matrix with positive-definite projection when needed | Extracted partial L, approximate |
| C | Single-reference Hammerstad/Jensen planar branch estimate | Approximate |
| G(f) | `omega * C * loss_tangent` where imported dielectric loss data covers the branch | Approximate |

For an explicit return net, planar C/G is assigned only where the signal-branch
midpoint projects onto return-net trace, pad, or zone copper on the selected
reference layer. Remote copper on the same layer is not treated as a plane.

Every port records positive-definite correction applied to L, normalized solve
residual, sampled condition number, least-squares fallback count, capacitance
branch coverage, dielectric-loss coverage, reference mode, and excluded vias.
The PDN multiport envelope additionally records reciprocity error, minimum
Hermitian-part eigenvalue, full complex Z matrices, and candidate provenance.
Its explicit source terminal is an ideal reference; this is not an extracted
power/ground differential port and therefore remains `Approximate`.

## Supported use

- Relative AC impedance screening for routed copper in the quasi-static range.
- Comparing revisions with unchanged extraction settings.
- Producing an inspectable RLCG network for external circuit processing.
- Importing explicitly reviewed scalar R/L/C/G equivalents into a visual
  SPICE workspace for staged ngspice execution. The importer does not fit or
  discard the source Z(f) sweep silently.
- Screening candidate capacitor locations with a traceable ideal-reference
  multiport reduction.
- Identifying where cleanup, an explicit return, or a higher-tier solver is required.

## Blocked use

- Sign-off characteristic impedance, delay, S-parameters, or eye diagrams.
- Via/antipad capacitance without drill, pad, antipad, and reference-plane field geometry.
- Proximity-effect conductor loss.
- Coupled multiconductor capacitance and modal transmission-line parameters.
- Full-wave propagation, radiation, dispersion, and anisotropic materials.
- Claiming iterative closed-loop field/circuit convergence from the current
  one-way PEEC-to-ngspice handoff.

## Accuracy gates

Numerical convergence alone does not make an extraction sign-off quality.
Promotion requires all of the following:

1. Mesh convergence on R, L, C, and the impedance sweep.
2. Passive/reciprocal matrices without material correction.
3. Bounded condition number and normalized residual.
4. Analytical microstrip, stripline, loop-inductance, and via fixtures.
5. Correlation against an independent electrostatic/PEEC/FEM solver.
6. Correlation against measured impedance or S-parameter fixtures.

The current corpus checks resistance units/invariance, planar sheet
convergence, hybrid topology, rectangular-conductor inductance, AC-loss
monotonicity, and the wide-microstrip parallel-plate capacitance limit. It does
not yet satisfy gates 4 through 6 for arbitrary PCB geometry.
