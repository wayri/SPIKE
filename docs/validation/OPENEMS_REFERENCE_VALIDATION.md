# openEMS Reference Validation Record

Historical version-bound record: the current adapter is 1.3.4, so the 1.1.0
evidence below is **not** attached to the current capability catalog. A local
three-level rerun for 1.3.4 passed the same limited fixture gate but remains
unpackaged. See
[the actual-grid increment](OPENEMS_ACTUAL_GRID_20260928.md). It has not yet
been promoted to packaged/version-matched release evidence.

## Decision

SPIKE's openEMS adapter version 1.1.0 is **reference-validated** with openEMS
0.0.36 for the official simple rectangular patch-antenna fixture. This permits
the solver manager to recommend that exact runtime for inspectable full-wave and
NF2FF execution. It does not validate arbitrary PCB layouts or compliance.

Machine-readable evidence is packaged at
`extensions/openems_suite/validation_data/openems-simple-patch-v1.json`. The catalog
applies it only when both the openEMS and adapter versions match.

Reproduce the gate with:

```powershell
spike openems-benchmark --mesh-resolution-mm 5 4 3 --max-timesteps 50000
```

## Fixture

- Reference: <https://docs.openems.de/python/openEMS/Tutorials/Simple_Patch_Antenna.html>
- Patch: 32 x 40 mm on a 60 x 60 mm ground plane
- Substrate: 1.524 mm, relative permittivity 3.38, loss tangent 0.001
- Excitation: explicit 50 ohm Z-directed lumped port
- Sweep: 1 to 3 GHz, 101 points
- Far field: 2.45 GHz, 37 theta by 73 phi samples
- Boundary: MUR with 70 mm air padding

## Results

| Mesh | Resonance | Minimum abs(S11) | Peak directivity | Runtime |
| --- | ---: | ---: | ---: | ---: |
| 5.0 mm | 2.20 GHz | 0.14287 | 4.7332 linear | 34.33 s |
| 4.0 mm | 2.28 GHz | 0.17907 | 4.7663 linear | 84.64 s |
| 3.0 mm | 2.32 GHz | 0.12852 | 4.8886 linear | 60.08 s |

For the finest pair, resonance changed by 1.724% against a 3% gate and peak
directivity changed by 2.502% against a 10% gate. All runs produced finite S11,
positive radiated power, positive directivity, and shape-checked NF2FF arrays.

## Defects Found By The Run

The executable benchmark found and drove corrections for:

- CSXCAD polygon coordinate layout;
- duplicate/near-duplicate mesh lines around ports;
- loss of critical conductor, dielectric, and port coordinates after smoothing;
- NF2FF frequency matching tolerance;
- missing bounded time-step controls;
- dielectric Z subdivision.

## Scope Limits

This evidence validates one geometry translator path, explicit lumped-port
construction, real FDTD execution, S11 normalization, NF2FF execution, and the
recorded mesh-convergence gate. It does not establish:

- arbitrary PCB, cable, enclosure, flex, or connector accuracy;
- regulatory emissions or immunity compliance;
- chamber correlation, antenna-efficiency calibration, or absolute field-level
  uncertainty;
- multiport calibration, material-library accuracy, or production mesh policy.

Those claims require additional analytical fixtures, measured boards, chamber
data, and independent solver comparison. Every arbitrary-board result therefore
continues to report its own unvalidated/validated state independently of the
runtime's reference-validation status.
