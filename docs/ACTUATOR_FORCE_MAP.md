<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Actuator force-map review

This executable increment reviews supplied fixed-excitation force/coenergy
maps for reluctance, permanent-magnet/voice-coil and electrostatic actuators.
It is **not** an actuator field solver, motion integrator or production qualification.
No private native implementation is imported by this public module.

```powershell
build/qualification-py311/Scripts/python.exe -m python.spike_core.actuator_force_map --request examples/actuator/voice-coil-force-map.json --result build/voice-coil-review.json
```

Other original examples are `examples/actuator/reluctance-force-map.json` and
`examples/actuator/electrostatic-force-map.json`. They are analytic fixtures, not
extracted fields or measured data. This local developer CLI is not the hardened
native job runtime. It reads at most 8 MiB, rejects duplicate/unknown fields and
limits each map to 4,097 samples. Output parent directories must exist.
The [request schema](../schemas/actuator-force-map-v1.schema.json) defines the
public data shape. The typed runtime additionally checks finiteness, equal
lengths, increasing coordinates and numerical range.

## Model and derivation

At fixed current, virtual work gives `F = partial W'(i,x)/partial x` for a
conservative magnetic system. At fixed voltage use electrical coenergy
`W'(V,x)` with the same positive derivative. For linear inductance and capacitance,
`W'=L(x)*i^2/2` and `W'=C(x)*V^2/2`, respectively. Do not substitute the negative
derivative of fixed-charge energy for the fixed-voltage law; source work differs.
For PM systems, include the complete displacement-dependent coenergy, including
the PM contribution, not only coil self-energy. Positive force follows increasing
`position_m`. A closing-gap coordinate has the opposite sign to gap width.

The review compares supplied force with a three-point second-order derivative
(one-sided at endpoints, centered inside, including nonuniform spacing). It also
compares trapezoidal integral of force with the coenergy difference. Both checks
must pass declared absolute and relative engineering tolerances. These are not
manufacturer or standard limits. Constant energy offsets do not change force.

Stroke, min/max force, peak-to-peak force and optional peak force per moving mass
are reported. Peak-to-peak force is **not** automatically cogging: identifying
cogging requires a zero-current PM map and matching mechanical convention.
Force/mass is a performance metric, not a coupled motion prediction.

## Evidence and remaining qualification

Run `python scripts/qualify_actuator_reference.py` for a machine-readable report
containing all 11 analytical/example runs, input digests, fixed thresholds,
four-grid errors and three deliberate force-sign corruptions. A failed criterion
returns exit code 1. These failures must be repaired at the responsible layer,
then the unchanged corpus rerun; do not relabel failed results as verified.

`tests/python/test_actuator_force_map.py` checks ideal magnetic-gap Maxwell
pressure, uniform-field Lorentz force, and electric-gap pressure against
coenergy differentiation; four stroke grids demonstrate second-order derivative
convergence. It tests reversed force, energy offsets, nonuniform spacing and
malformed inputs. These independently authored equations are verification
oracles, not a new research algorithm. Consistency can pass when both supplied
maps share an error; independent field/measurement evidence remains mandatory.

Full workflows still need geometry/material/coil or electrode compilation,
field solves over displacement, air-control-surface force and virtual-work
agreement, mesh/air-box/stroke convergence, nonlinear materials and PM handling,
motion coupling, and public measured validation. Electrostatic qualification also
needs mechanical stability/pull-in and breakdown applicability limits. No input
map, citation or passing review changes `production_qualified: false`.

See [current research and delivery plan](SERDES_ACTUATOR_DELIVERY.md).
