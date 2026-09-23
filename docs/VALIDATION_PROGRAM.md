# Solver Verification, Validation, and Standards Program

## Current Status

The installed corpus currently checks ten bounded properties: straight-trace DC resistance, plated-via resistance, square-zone convergence, hybrid trace/zone/pad/via connectivity, native straight-trace inductance, native hybrid PEEC execution, a wide-microstrip capacitance asymptote, AC-resistance monotonicity, a closed-form shared-reference two-port resistor matrix, and PDN two-port capacitor loading against an independent nodal re-solve.

A passing run is an implementation verification result. The closed-form matrix
and independent nodal re-solve verify circuit assembly and network reduction;
they do not validate arbitrary PCB multiport extraction. A passing run is not
global solver certification.

## Required Gates

| Gate | Evidence | Current state |
| --- | --- | --- |
| Unit and analytical verification | Closed-form fixtures with explicit tolerances | Implemented for bounded cases |
| Mesh convergence | Three or more refinements; quantity-of-interest stability | Implemented for square-zone DC fixture |
| Independent implementation | Comparison against a separately implemented method or trusted solver | Implemented only for the PDN two-port circuit reduction; PCB extraction remains incomplete |
| Measurement correlation | Characterized fixtures with uncertainty budget | Not implemented |
| Applicability envelope | Frequency, geometry, material, conditioning, and mesh limits | Partially documented |
| Regression control | CI failure on tolerance regression | Implemented for current corpus |
| Release claim | Mode-specific accuracy statement approved from evidence | Not permitted yet |

## Standards Alignment

- IPC-2152 is the reference framework for current-carrying capacity and acceptable conductor temperature rise. It is a thermal/current-capacity standard, not a substitute for field-solver validation: https://www.ipc.org/TOC/IPC-2152.pdf
- IPC design standards identify IPC-2141, IPC-2152, IPC-2221/2222, and related board-design scopes that should inform design-rule and warning policies: https://www.ipc.org/ipc-design-standards
- IEEE 370-2020 provides practices for high-frequency interconnect measurement quality up to 50 GHz and will govern fixture/de-embedding evidence for future SI validation: https://standards.ieee.org/ieee/370/6165/
- IPC TM-650 supplies relevant electrical and material test methods, including conductor resistance, plated-through-hole resistance, dielectric constant, and dissipation factor methods: https://www.ipc.org/test-methods
- ASME V&V 20 provides a framework for quantifying validation accuracy using both simulation and experimental uncertainty for CFD and heat transfer. It applies to future OpenFOAM validation rather than current electrical results: https://www.asme.org/codes-standards/find-codes-standards/standard-for-verification-and-validation-in-computational-fluid-dynamics-and-heat-transfer/2009

## Electrical Fixture Roadmap

1. Manufacture four-wire copper coupons over several widths, thicknesses, and finishes.
2. Measure via chains with Kelvin structures and cross-sections for actual plating thickness.
3. Measure plane/zone spreading resistance with multiple terminal geometries.
4. Build impedance coupons and IEEE 370-quality fixtures for microstrip, stripline, differential, and via transitions.
5. Record VNA, TDR, DC, thermal-camera, and material-coupon uncertainty.
6. Compare SPIKE against measurements and at least one trusted independent implementation.
7. Publish raw design files, calibration data, scripts, meshes, results, and uncertainty budgets where licensing permits.

## Correction Policy

When a fixture fails, the correction must be made at the responsible model boundary: geometry normalization, mesh topology, material model, terminal model, matrix assembly, numerical solve, or postprocessing. Tolerance widening is not a correction unless the applicability claim is narrowed and the physical evidence justifies the new bound.
