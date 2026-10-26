<!-- SPDX-License-Identifier: Apache-2.0 -->
# Live sampled EM / owned-SPICE linear AC coupling

## Bounded claim and actual backend

On 23 October 2026, `run_em_spice_coupling` executes a coupled sampled passive
EM network and a typed linear RLC circuit with independent complex sources.
Each exact positive frequency is solved by the actual release-owned SPIKES C++
operating-point engine. The owned runner has **no native AC execution route**.
The explicit method is therefore
`frequency_domain_real_block_owned_spice_operating_point`, not native SPICE AC.
The service is not an export-only path: EM coefficients and circuit branches
participate in the same executed system, and the returned physical currents,
voltages and powers are reconstructed from that native solution.

No native numerical kernel, arbitrary-netlist interface, DLL selection, model
file loading or shell execution was added. This bounded reference/composition
service is not a replacement production/HPC kernel. Nonlinear bias/small-signal
devices, behavioral sources, arbitrary subcircuits, broadband causal fitting,
transient EM feedback and temperature-dependent re-solving are unsupported.
Results remain experimental and not production qualified. Synthetic code
verification is not EM field validation, device qualification or measurement.

## Reviewed foundations and independent formulation

Reviewed on 23 October 2026:

- K. Kurokawa, *Power Waves and the Scattering Matrix*, IEEE TMTT 13(2),
  194-202 (1965), DOI [10.1109/TMTT.1965.1125964](https://doi.org/10.1109/TMTT.1965.1125964).
  [Reviewed paper](https://athena.ecs.csus.edu/~milica/EEE211/HL/kurokawapowerwaves.pdf),
  printed pages 194-195, equations (1), (7), (10): wave/terminal transformation
  and actual transferred power. Only common positive real reference impedance
  is used here; the paper's broader complex-reference cases are not implemented.
- C.-W. Ho, A. E. Ruehli and P. A. Brennan, *The Modified Nodal Approach to
  Network Analysis*, IEEE TCAS 22(6), 504-509 (1975), DOI
  [10.1109/TCS.1975.1084079](https://doi.org/10.1109/TCS.1975.1084079).
  [Reviewed paper](https://spinningnumbers.org/assets/MNA75.pdf), section II,
  printed pages 504-505, equations (1)-(3): nodal KCL and extra branch-current
  variables for voltage constraints; capacitor constitutive relation. The
  paper's transient discretization and pivoting algorithm are not implemented
  by this adapter.

The derivation, code, controlled-source lowering, circuit fixtures, oracles and
prose below are independently authored SPIKE material. No external source code,
test circuit, dataset, figures or implementation was copied or translated.

Let physical phasors use RMS amplitude and `exp(+j*omega*t)` with frequency in
Hz and `omega=2*pi*f` in rad/s. Branch current is positive from positive_node
to negative_node. Define the branch incidence vector with +1 at the positive
node and -1 at the negative node, excluding the explicit datum node. Ohm's law,
`i=C*dv/dt` and `v=L*di/dt` give branch admittances `1/R`, `j*omega*C` and
`1/(j*omega*L)` in S for positive R (ohms), C (F), L (H). DC is deliberately
excluded rather than substituting a finite admittance for an ideal inductor.
Independent voltage-source currents are additional MNA unknowns in A; their
voltage equations use the declared RMS phasors in V. Independent current-source
phasors are in A. Superposition is exact within this declared linear model.

For EM use `S[receive][excited]`, common real `Z0>0` in ohms, and current into
each EM positive terminal. Define `a=(V+Z0*I)/(2*sqrt(Z0))` and
`b=(V-Z0*I)/(2*sqrt(Z0))` in sqrt(W). Let `q=sqrt(Z0)*a`, in V, and `b=S*a`.
It follows directly that `V=(identity+S)*q` and
`I=(identity-S)*q/Z0`. If B contains the port incidence vectors as columns,
the coupling adds `B*(identity-S)*q/Z0` to circuit KCL and adds the equations
`transpose(B)*v-(identity+S)*q=0`. This uses every named port and its explicit
polarity; no S-to-Y/Z inverse is needed, so ideal throughs are admitted when
the connected circuit is nonsingular. Reference-plane labels are metadata,
not a phase correction, de-embedding operation or calibration.

Writing the resulting equations as `A*x=h`, split real and imaginary parts:

```text
[ Re(A)  -Im(A) ] [ Re(x) ] = [ Re(h) ]
[ Im(A)   Re(A) ] [ Im(x) ]   [ Im(h) ]
```

Each real row is divided by its largest coefficient magnitude. A generated
voltage-controlled current source from equation node r to ground, controlled
by unknown node c relative to ground, contributes the scaled coefficient
times x[c]. A current source from ground to node r contributes the scaled
right-hand side. Native SPICE `.op` KCL therefore solves exactly this real
block (up to floating-point arithmetic). These artificial node values encode
SI numerical coordinates: some represent V and some A. Artificial native
element powers have **no physical meaning and are never reported as heat**.
Only reconstructed original circuit and EM-terminal observables are physical.

Parent-agent independent derivation of the wave-incidence equations and real
block agreed before final verification. This is supporting review, not the
knowledgeable human numerical review required before release.

## Admission, conditioning and conservation

The sampled-network admission owner retains port order and exact source
frequencies; no interpolation, extrapolation, renormalization, phase unwrap,
clipping or causality claim occurs. Full-matrix SVD requires each EM sample's
largest singular value <= `1+1e-10`. Circuit RLC values are positive. This
workflow is specifically passive EM with explicitly driven linear circuits;
it does not silently reinterpret intentionally active EM data as passive.

The row-scaled real system's 2-norm condition number must be finite and <=1e10.
This bound refers to the declared SI numerical coordinates and is conservative,
not a unit-invariant physical accuracy guarantee. Empty/singular equations,
ideal-source conflicts, floating common modes and poorly conditioned cases are
rejected without regularization, gmin insertion or relaxed tolerances. No
frequency-refinement convergence is claimed: the supplied model is solved only
at exact samples; interpolation error and full-wave discretization are absent
from this adapter's error budget.

After actual native execution, all of these independent reconstructions must
pass relative tolerance 1e-10 (with only the smallest normal floating-point
number as the zero-scale floor):

- Every real equation: `abs(Arow*x-hrow) / (sum(abs(Arow*x))+abs(hrow))`.
- Every physical circuit node: signed original-branch plus EM-port current
  sum divided by the sum of those separate current magnitudes.
- Every voltage-source constraint and every EM terminal/wave voltage relation.
- Every port's `Re(V*conj(I))=(abs(q)^2-abs(S*q)^2)/Z0` power identity.
- Total source power supplied equals resistor heat plus net EM-port power.

Strong excitation cannot hide a weak row, node or port failure through a
global norm. Pure reactance is not resistor heat. For RMS phasors there is no
factor one-half. EM net power can include radiation and unclassified losses;
it is never assigned automatically to thermal cells.

## API and trust/resource boundary

`python/spike_core/em_spice_coupling.py:run_em_spice_coupling(request,
cancel_check=None)` accepts exactly these five fields:

```text
contract: "spike/em-spice-coupling-request/v1"
source: existing five-field sampled-network source
wave_convention: "rms_power_waves_common_positive_real_reference"
circuit: {ground_node, elements}
port_bindings: {port_name: {positive_node, negative_node, reference_plane}}
```

Unknown fields are rejected. Each RLC element has exactly
`{id,type,positive_node,negative_node,value}`; value is its SI R, L or C, not a
SPICE expression. Each independent voltage/current source instead has exactly
`{id,type,positive_node,negative_node,phasor}`, with `[real,imaginary]` phasor.
The supported types are resistor, capacitor, inductor, voltage_source and
current_source. Every EM terminal must name an existing circuit node; no
topology, contact, reference plane or missing port is inferred. Case-ambiguous
node IDs and duplicate/reversed duplicate port terminal pairs are rejected.
Independent-source phasors are constant over the supplied frequency sweep.
RLC values are ideal lumped parameters; their physical applicability at any
chosen frequency is a separate engineering assumption, not admitted from
their numerical range alone.

Use the `network_source`, `port_bindings` and `wave_convention` from the
existing reviewed EMerge preparation packet. Retain that complete packet,
original AnalysisResult, warning issues, source status and provenance as
companion artifacts: the generic five-field source does not contain those
fields, and this adapter cannot authenticate an EMerge solve from it alone.
The source digest binds exactly that generic source; it does not elevate it
to independently calibrated field data.

Bounds are 8 MiB request, 16 MiB public result, 1..64 source frequencies in
`0<f<=1e15` Hz, 1..16 EM ports, 64 non-ground nodes and 128 circuit elements.
RLC SI values must lie in 1e-18..1e18; complex sources are bounded as in the
existing AC helper. The real block is capped at 416 equations and 16384 nonzero
coefficients. Generated netlists are capped at 2 MiB, and native return JSON
at 8 MiB. There is one native operating-point execution per sample. Native
paths are fixed by the existing release-owned resolver, never request text;
the reported native library must match that resolver. The library SHA-256 is
checked before/after the run and native source SHA-256 must match the generated
netlist. No DLL host path is published in the new result.

Cancellation is polled during source admission and before/after each native
call. There is no in-kernel cancellation or hard wall-time deadline. The
existing supervised worker process must provide in-flight termination and
memory/time isolation. Any admission, native, conditioning, residual, size or
cancellation failure returns no completed partial coupled result.

Results include original-node/element phasors, EM-port V/I/waves, original
resistor heat, unclassified EM power, power/residual diagnostics, input/source
digests, library identity, generated-netlist digest and sanitized native-result
digest. The native diagnostics are retained but do not replace the physical
post-solve gates.

## Executed verification

Environment: Windows, Python 3.12.9, NumPy 2.4.2. Actual owned DLL
`spikes_c_api.dll` SHA-256:
`b739b802962952aa6b1f59f08d46bfde3384e4f6c27e99a8937162e43efe1e0f`.

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:TEMP=(Join-Path (Get-Location) '.local/test-temp')
$env:TMP=$env:TEMP
./.venv/Scripts/python.exe -m unittest tests.python.test_em_spice_coupling tests.python.test_owned_spice_workspace tests.python.test_em_network_cosimulation -v
./.venv/Scripts/python.exe scripts/check_architecture.py
```

Executed 30 tests, zero skips, 0.359 s unittest duration; architecture guard
passed. Fifteen new tests cover actual engine execution and independent
closed-form checks, plus adjacent owned-SPICE/EM regressions. Numerical cases:

- 2 V RMS, 25 ohm series resistor, 50 ohm EM matched load: expected
  `Vport=4/3 V`, `Iport=2/75 A`. Also compared against a separately constructed
  physical resistor-divider `.op` netlist executed by the same native engine,
  without calling the lowering helper to construct the reference circuit.
  Observed coupled power discrepancy was 6.938893903907228e-18 W,
  maximum per-node KCL relative error 1.3010426069826053e-16, and scaled
  connection condition 2.7173640843561517.
- Independently derived series R=25 ohms, L=40 uH, shunt C=3 nF with matched
  50 ohm EM port at 1000, 12345 and 900000 Hz. With
  `Vs=2*exp(0.37j) V`, the oracle uses
  `Y=1/50+j*omega*C`, `V=Vs/(1+(R+j*omega*L)*Y)`, `Iseries=Y*V`.
  Voltages, inductor/capacitor currents and resistor heat are asserted, not
  just shape or conservation. Complex tolerances are `1e-14+2e-11*abs(reference)`;
  resistor heat and balance use 1e-13 W absolute on these fixtures.
- Ideal through and a separately specified complex series impedance using
  `S11=Z/(2*Z0+Z)`, `S21=2*Z0/(2*Z0+Z)` and a 75 ohm load. The independent
  circuit oracle is `I=2/(25+Z+75)`. A nonreciprocal two-port fixture and a
  complete port permutation catch receive/excitation transposition.
- Differential non-ground return and reversed polarity; imaginary current
  source; exact zero excitation; 1e-6 and 1e-12 V scaling.
- Actual native result corruption checks: digest/library mismatch, failed
  status, node error, and a weak-node error under simultaneous 1e8 and 1e-6 V
  sources. Corruption is deliberately injected **after an actual engine run**;
  no passing numerical reference is mocked.
- Unsupported devices/raw text, invalid reference planes/nodes, nonpassive
  data, DC, malformed values, excessive nodes/samples, a singular
  open/current-source connection, an ill-conditioned ideal-short connection
  with 1e-15 ohm series resistance, and cancellation before/after native
  execution fail closed.

This evidence establishes only the declared synthetic linear mathematical
boundary. No fresh EMerge solve, external circuit-engine parity, measured EM
correlation, arbitrary nonlinear SPICE, general transient coupling, complete
release suite or knowledgeable human numerical release review is claimed here.
