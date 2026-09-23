# Power-Loop Parasitic Extraction

SPIKE's `spike/loop-parasitics/v1` result represents an explicit pad-to-pad
forward conductor and an explicit pad-to-pad return conductor. Each conductor
may cross copper layers through extracted vias, pads, tracks, and zones. The
loop solve retains mutual partial inductance, so the reported geometry value is
the loop quantity rather than the sum of two isolated net inductances.

## Setup

Use **PI > Net manager > Loop RLC** to select:

1. A forward net and its source-side and load-side pads.
2. A distinct return net and its load-side and source-side pads.
3. An optional Power Tree path group containing reviewed series components.

Pad anchors carry all connected copper layers. The selected Power Tree path
supplies explicit input/output pin groups, the component geometry center, and
reviewed R/L/C or operating-point data. Unreviewed and ambiguous component
models block the extraction.

## Numerical Scope

- Resistance and loop inductance use the connected hybrid conductor graph.
- The PEEC impedance matrix retains forward/return mutual partial inductance.
- Stitched layers are traversed through extracted via and pad branches.
- Linear series component R/L/C is added to the impedance sweep; the result
  also reports the equivalent series capacitance of reviewed in-path models.
- Nonlinear devices, including MOSFETs, contribute only a reviewed
  operating-point linearization; switching behavior belongs in the linked
  ngspice study.
- Capacitance is currently a bounded, single-reference stackup estimate using
  the imported dielectric properties. It is emitted only when the loop return
  net matches the solve's explicit capacitance reference.

The implementation is therefore suitable for comparative quasi-static
screening. Capacitance and arbitrary-board sign-off remain gated on correlation
with a multiconductor electrostatic solver or measurement.

## Contract Sketch

```json
{
  "id": "vin-switch-loop",
  "forward": { "net": "VIN", "source": {}, "load": {} },
  "return": { "net": "PGND", "load": {}, "source": {} },
  "component_models": [
    {
      "reference": "Q1",
      "model_kind": "linearized_operating_point",
      "input_pins": ["Q1.5", "Q1.6"],
      "output_pins": ["Q1.1", "Q1.2"],
      "geometry_center_mm": [42.0, 18.0],
      "reviewed": true
    }
  ]
}
```
