<!-- SPDX-License-Identifier: Apache-2.0 -->
# Generic multi-terminal lumped parts

## Studio workflow

Open **Physics models** from the component catalog or Parts browser. Select a
template, enter its labeled SI coefficients, inspect the complete terminal
symbol and model limitations, then export the `.lib` subcircuit. The generated
model may be reviewed and imported through the existing SPICE paste/library
workflow; browsing alone does not alter a circuit or select a different solver.
This does not implement a compact graphical hierarchical-instance placement.

The 11 original device symbols are available in the symbol library, including
NMOS/PMOS bulk, NPN/PNP substrate, dual-gate, JFET, Kelvin, substrate resistor,
feedthrough capacitor and coupled-winding drawings. Geometry-only PMOS/PNP,
dual-gate and JFET entries do not enable unsupported native physics. Native
NPN remains three-terminal; native NMOS uses all four persisted terminals.
Existing pin anchors and document order are unchanged by transistor glyphs.

`python scripts/export_spikes_physics_library.py --output NEW_DIRECTORY` writes
five original `.SUBCKT` models, a conventional symbol JSON library, an importable
symbol-only `.spklib` and a digest manifest. It refuses to overwrite an existing
directory. These formats keep executable model source separate from geometry.

`python/spikes/lumped_physics_parts.py` builds five original, inert `.subckt`
templates. These are generic, unqualified circuit approximations, not vendor
models, TCAD, process extraction, production BJT/MOS models or hardware evidence.
The Python module composes existing native primitives; it does not add a solver,
change the selected backend, or execute a circuit while browsing/building.

## API and use

`catalog()` returns independent JSON-compatible descriptors with `id`, display
`name`, ordered `pins`, SI `defaults`, `symbol_id`, `backend`, `supported_analyses`,
`model_status` and `limitations`. `build(kind, parameters=None,
name="SPK_LUMPED")` returns this metadata plus `kind`, the chosen subcircuit
`name`, normalized `parameters`, and the complete `source`. Its status is always
`generic_unqualified`; `backend="native"` declares a target, not automatic
backend selection. The documented analysis subset is operating point,
backward-Euler transient, and BDF2 transient.

```python
from python.spikes.lumped_physics_parts import build

part = build("nmos4", {"body_effect_sqrt_v": 0.4}, name="MY_NMOS")
deck = part["source"] + """
X1 drain gate 0 bulk MY_NMOS
VD drain 0 4
VG gate 0 3
VB bulk 0 -1
.op
"""
```

All numerical input uses SI units, including capacitance in farads, inductance
in henries, and transit time in seconds. Unknown keys, non-mapping parameter
objects, strings, booleans, nonfinite numbers and out-of-range numbers raise
`ValueError`. Names admit only ASCII identifiers of at most 64 characters;
parameters cannot inject source. Ranges are numerical admission bounds, not a
physical validity envelope. Large R/C/L ratios can still make the MNA problem
ill-conditioned; convergence diagnostics and timestep refinement remain required.

## Exact topology and limits

| ID | Ordered pins | Implemented topology |
| --- | --- | --- |
| `nmos4` | D G S B | Level-1 NMOS core, body-anode/drain-cathode and body-anode/source-cathode Shockley junctions; explicit constant CGB, CBD, CBS; core CGS, CGD, CDS |
| `npn4` | C B E SUB | Three-terminal Ebers-Moll NPN, SUB-anode/collector-cathode Shockley junction, constant CSUB; core CBE, CBC, TF, TR |
| `resistor3` | P N SUB | Two R/2 body segments; capacitance and leakage resistance from their internal midpoint to SUB |
| `feedthrough_capacitor3` | IN OUT GND | Series R from IN to midpoint, L from midpoint to OUT, C from midpoint to GND |
| `kelvin_shunt4` | FP FN SP SN | Existing `passive_models.build_model("kelvin_shunt", ...)`: force contacts and body resistor between sense pins |

NMOS and NPN substrate ports use an exact internal 0 V link. This preserves
their electrical voltage and total current while keeping primitive endpoints
distinct when the caller ties B to S or SUB to C; the parser otherwise rejects
two-terminal primitives whose nodes collapse. The link adds no resistance or
voltage offset. The NMOS bulk remains a true connected terminal, not a label.
The NPN is explicitly an X-subcircuit; no four-terminal Q parser syntax or
production substrate transistor model is claimed.

Optional capacitances and inductance may be zero. Zero inductance uses an exact
0 V link; it never disconnects the feedthrough. Primary resistance and
feedthrough capacitance must be positive. Other external ideal-source loops,
floating terminals, or collapsed primitives remain the caller's responsibility.

The explicit diodes obey the native Shockley junction law. They do not model
reverse recovery, avalanche, depletion-charge nonlinearity or temperature
feedback. All added capacitances are constant. The native Level-1 core retains
its body-effect law with forward body bias clamped in the threshold calculation;
adding body diodes does not repair that core approximation. The NPN has no
substrate carrier transport, parasitic transistor, latch-up, Early effect or
high-injection physics. Neither PNP nor PMOS is fabricated by these templates.
Feedthrough topology is asymmetric and lumped, not an RF package model.

The model-card core charge requires a native DLL with compact-charge support.
BE/BDF2 are the admitted transient methods. Hybrid trapezoidal is rejected by
the native engine for these compact transistor cores, even if their charge
parameters are zero. No external engine substitution is performed.

## Original derivation and verification

This work is an original composition of existing SPIKE-owned primitives and
independently authored circuit-law oracles. No external implementation, model
card, vendor parameter data or third-party source was copied or adapted.
Numerical kernel behavior is inherited, not newly qualified by this composition.

For each added junction, `I = IS * (exp(V/(n*kT/q)) - 1)`. Its two equal and
opposite terminal stamps conserve current. Each constant capacitor stores
`Q = C*(Va-Vb)` with equal/opposite terminal charge. An exact 0 V bulk link
preserves port power and current conservation. At VGS=3 V, VDS=4 V, the Level-1
saturation oracle is `ID = KP/2*(3-VTH)^2*(1+4*LAMBDA) + 4*Goff`, with
`VTH = VTO + GAMMA*(sqrt(PHI+max(0,-VB))-sqrt(PHI))` when source is zero.
The body junction reverse leakage is below the fixture's absolute tolerance.

For the R=1000 ohm resistor with a 1000 ohm midpoint substrate leak, P=1 V,
N=SUB=0 gives midpoint 0.4 V by KCL; P current is 1.2 mA and substrate current
is 0.4 mA. Feedthrough steady state has open C and short L, hence a 1 ohm load
with 0.01 ohm series resistance gives VOUT=1/1.01 V. With L=0 and no load,
the BE capacitor recurrence is
`v[n] = (vin[n] + (RC/h)*v[n-1])/(1+RC/h)`.
The gate ramp oracle uses `I=C*dV/dt`: 1 nF CGS plus 2 nF CGB at 1 V/us
requires 3 mA. The Kelvin unloaded sense voltage is the body fraction of the
force voltage, `Rbody/(Rbody+2*Rcontact)`.

`tests/python/test_spikes_lumped_physics_parts.py` tests exact terminal mapping,
model scoping, malformed inputs, optional-zero topology, independent body
threshold response, body/substrate junction current and terminal KCL, passive
DC, BE charge recurrence, BE/BDF2 gate charge, and hybrid rejection. Native
tests skip unless an explicit current DLL is provided:

```powershell
$env:SPIKES_TEST_LIBRARY = "C:\path\to\spikes_c_api.dll"
python -m unittest tests.python.test_spikes_lumped_physics_parts -v
```

Executed development evidence (2026-10-13): the 12 focused tests passed against
`build-spikes-sine-20261012/Release/spikes_c_api.dll`, SHA-256
`2CC08782E6A1503BD268288DC3488E2BC05841DC764DD321D5AD9E600A9A9682`.
Current-oracle tolerances are 1e-10 to 1e-12 A; voltage tolerances are 1e-9 to
1e-10 V. This is bounded implementation evidence, not process, manufacturer,
frequency-envelope or hardware qualification. Knowledgeable human numerical
review is required before release.
