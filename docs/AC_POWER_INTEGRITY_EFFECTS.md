# Explicit AC power-integrity effects

`analyze_ac_power_integrity` accepts `{request: ...}` with contract
`spike/ac-pi-request/v1` and returns `spike/ac-pi-result/v1`. The schemas in
`schemas/ac-pi-*-v1.schema.json` describe the JSON boundary. This is an
experimental explicit uniform-line reference diagnostic, not a board extractor
or a replacement for native PEEC. It requires knowledgeable numerical review
before release. RMS phasors use `exp(+jωt)` and a 1 V RMS Thevenin source.

## Distributed line and loaded voltage

Supply length in metres, R in ohm/metre, L in henry/metre, G in siemens/metre,
C in farad/metre, an ascending frequency list (DC allowed), and explicit complex
source/load impedances `[real, imaginary]`. A null load is open circuit; `[0,0]`
is a short. Resistive parts must be nonnegative. Frequencies are capped at 2048.

Independently integrating `dV/dx = -z I`, `dI/dx = -y V` over length gives
`q² = z y l²`, `A = D = cosh(q)`, `B = z l sinh(q)/q`,
`C = y l sinh(q)/q`. The implementation uses a small-q series and does not divide
by `sqrt(z/y)`, so the pure DC resistance and open-load limits remain defined.
Here `z=R+jωL`, `y=G+jωC`. Electrical attenuation above 300 nepers is rejected.

With the receiving-end state `(Vr,Ir) = (vl,il) scale`, use `(1,0)` for an open
load and `(Zload,1)` otherwise. Then
`scale = 1/[A vl+B il+Zsource(C vl+D il)]`. Returned complex voltages,
current and input impedance are directly evaluated from that state. Open input
impedance is null with an explicit state.
Only exactly zero input current marks an open impedance; finite high impedance
retains its computed value. Only exactly zero sending voltage leaves its ratio
undefined. Finite voltage ratios are checked for representable range, without
an absolute current or voltage threshold dependent on the selected units.
A denominator margin below 1e-12 is
reported as singular, with no fabricated finite voltage. This guard also catches
ideal quarter-wave open/zero-source-resistance resonance.

Ferranti evidence compares receiving voltage with **sending terminal voltage**,
not the unloaded source EMF. For a lossless open line,
`Vr/Vsend = sec(βl)`: before quarter wave it exceeds one. Finite source impedance
and load change that response. Board-size traces do not necessarily show a
meaningful low-frequency rise; the workbench permits explicit reference cases.

The equation reference is author Michael Steer's
[transmission-line models, section 2.7](https://eng.libretexts.org/Bookshelves/Electrical_Engineering/Electronics/Microwave_and_RF_Design_II_-_Transmission_Lines_%28Steer%29/02%3A_Transmission_Lines/2.07%3A_Models_of_Transmission_Lines).
Only equations guided this independently authored implementation.

## Slab skin and imposed-field proximity loss

Optional `conductor` supplies width, thickness, conductivity, relative permeability,
and complex `field_bias_ratio = Havg/Hdiff`. It replaces explicit line R with
computed Joule resistance, avoiding double counting. It does not infer that
ratio from spacing, PCB return paths or nearby currents. The slab is infinite
in lateral extent; width scales total current and power but does not model
edge crowding. It represents one conductor; return-conductor loss is not added
automatically. Explicit line L remains unchanged by default. Opt-in internal
reactance and RMS roughness controls are described in
[High-frequency conductor loss](HIGH_FREQUENCY_LOSSES.md); enabling internal
reactance requires external-only L and zero imposed field bias.

Let half thickness be `a`, `k²=jωμσ`, and signed tangential surface fields be
`Hleft`, `Hright`. Define `Havg=(Hright+Hleft)/2`,
`Hdiff=(Hright-Hleft)/2`. Solving diffusion with both boundary values gives
`H(x)=Havg cosh(kx)/cosh(ka)+Hdiff sinh(kx)/sinh(ka)` and `J=dH/dx`.
Ohm's law gives surface E values; integrating the diffusion equation against
`H*` yields Joule power per length
`P/l = 2w/σ [Re(k tanh(ka)) |Havg|² + Re(k coth(ka)) |Hdiff|²]`.
The RMS convention introduces no factor 1/2. Total current is `2w Hdiff`.
The average-field term models proximity loss under **imposed** external fields.

At DC, `k coth(ka) -> 1/a` and `k tanh(ka) -> 0`; resistance tends to
`1/(σwt)`. Series expansions avoid cancellation and singular hyperbolic division
for small arguments. Deep-skin symmetric excitation tends to
`1/(2σwδ)`; one-face excitation doubles it. Equal fields can dissipate eddy-current
power with zero net current: the scalar kernel returns null effective resistance
in that case. The workbench fixes unit current and bounded nonzero thickness.

The primary magnetic-diffusion reference is Haus and Melcher's
[MIT Electromagnetic Fields and Energy, section 10.7](https://web.mit.edu/6.013_book/www/chapter10/10.7.html).
The two-face superposition, power identity, series and test oracles were derived
independently; no upstream implementation was inspected, copied or adapted.

## Acceptance evidence and boundaries

`tests/python/test_ac_power_integrity.py` checks DC/open/short limits, matched
lossless propagation, open and light-load voltage rise, ideal resonance refusal,
second-order convergence of independently composed lumped π ladders, DC/deep-skin
and one-face limits, and a 128-point independent volume integral of `|J|²/σ`.
Tests also check invalid inputs and the worker method. Analytical reference
agreement does not validate board models or arbitrary conductor configurations.

Native PEEC continues to represent isolated-slab resistance and optional
Hammerstad roughness, not geometry-derived proximity redistribution. This new
diagnostic does not inject guessed proximity into PEEC. Arbitrary-geometry AC
current redistribution, radiation, dielectric/material dispersion, nonlinear
loads, magnetic saturation, vias, launches, full-wave coupling, measurement
correlation and compliance remain outside this model.
