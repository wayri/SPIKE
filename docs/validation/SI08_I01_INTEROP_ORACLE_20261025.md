<!-- SPDX-License-Identifier: Apache-2.0 -->

# SI08-I01 independent mixed-mode interoperability oracle

Date: 25 October 2026. Scope: the existing `mixed_mode_network` owner in
`python/spike_core/solvers/signal_integrity/networks/sparameter_modes.py` and
its existing S/Z/Y input conversion owner. No numerical kernel is changed.
The companion test is `tests/python/test_si08_interoperability_oracles.py`.
This evidence supports the frozen I01 integrated campaign; it does not alone
complete a file-format, external measurement or release gate.

## Primary foundations actually reviewed

- R. B. Marks and D. F. Williams, *A General Waveguide Circuit Theory*,
  Journal of Research of NIST 97(5), 533-562 (1992), accepted 22 May 1992,
  [NIST original](https://nistdigitalarchives.contentdm.oclc.org/digital/api/collection/p16009coll6/id/74796/download).
  Reviewed section 3.4, p. 547, equation (61): receiver-row/source-column
  scattering convention; section 3.6, p. 548, equations (72) and (77):
  voltage/current impedance and admittance definitions; section 5, p. 555,
  equations (121)-(123): real-positive-reference power waves and net power.
  The text extraction was reviewed; the web PDF screenshot fetch failed.
- Keysight E5071C online help, [Evaluating Balanced Devices](https://helpfiles.keysight.com/csg/e5071c/measurement/fixture_simulator/evaluating_balanced_devices_balance_unbalance_conversion.htm),
  live page reviewed 25 October 2026 (no edition identifier displayed),
  sections Overview, Mixed Mode S-parameter and Procedure for Balance-Unbalance
  Conversion: equal impedances within a physical pair and explicit ordered
  physical-to-logical port assignment. This is the guide already linked by
  `docs/PI_SI_PARITY_EXECUTION.md`.

Only primary theory and specification material was consulted. No external
implementation, example, fixture or vendor measurement data was inspected or
adapted. The derivation, synthetic data and oracle below are independently
authored SPIKE material under Apache-2.0.

## Independent derivation and oracle construction

Use RMS phasor voltage V in volts, current I in amperes directed into each
port, and real positive reference R in ohms. Define power-normalized waves
`a=(V+RI)/(2 sqrt(R))`, `b=(V-RI)/(2 sqrt(R))`, with units sqrt(watt).
Subtracting the squared magnitudes gives `|a|^2-|b|^2=Re(V conj(I))`.
The test takes these port definitions as its foundation, not the production
matrix transform or the legacy adjacent-pair helper.

For an ordered positive/negative pair define
`Vd=Vp-Vn`, `Id=(Ip-In)/2`, `Vc=(Vp+Vn)/2`, `Ic=Ip+In`.
Expanding `Vd conj(Id)+Vc conj(Ic)` cancels the cross terms and leaves
`Vp conj(Ip)+Vn conj(In)`. Thus the pairing preserves port power.
The matched modal reference values are `Rd=2R`, `Rc=R/2`; singleton references
are retained. References can differ between pairs.

For each modal source column j, the oracle sets incident modal voltage to
`sqrt(Rm[j])` and incident modal current to `1/sqrt(Rm[j])`, all other entries
zero. It recovers physical incident voltages and currents through
`Vp=Vc+Vd/2`, `Vn=Vc-Vd/2`, `Ip=Id+Ic/2`, `In=-Id+Ic/2`.
Physical waves follow from the port definitions; the supplied physical S
acts on each excitation. Reconstructing total physical V/I, then applying
the modal V/I definitions, yields outgoing modal waves. Each outgoing
column is the expected derived S column. Returned incident modal waves must
equal the identity, and returned net modal power must equal physical power.
No production mixed-mode conversion or S/Z conversion helper supplies
expected results.

The independent representation check starts from an asymmetric, complex,
diagonally dominant impedance Z. For a unit physical incident source a,
substitute `V=ZI` into `V+RI=2 sqrt(R) a`, solve
`(Z+diag(R)) I=2 diag(sqrt(R))`, then form b from V/I. The same original Z
and its independently solved inverse Y are submitted to production, and
the resulting mixed S is compared with the physical oracle. This catches
incorrect multiplication order when pair references differ.

## Executed coverage and numerical acceptance

The ten tests pass with NumPy 2.2.6 in the existing `.venv-emerge3` interpreter:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv-emerge3/Scripts/python.exe -B -m unittest tests.python.test_si08_interoperability_oracles -v
```

- Every integer port count 2 through 64: two original asymmetric complex
  samples, supplied DC and 2.75 GHz, outside-in pairs, odd singleton ports,
  differing pair references, complete mapping and physical-power checks.
- A separate sparse five-port closed-form directional transfer checks unequal
  forward/reverse response; polarity reversal changes only the relevant
  differential row and column signs.
- A seven-port case checks physical relabeling with retained named identity,
  reordered pairs and reordered multiple singletons.
- S, Z and Y equivalence for 2, 3, 7, 16 and 64 ports. The boundary-current
  solve must have 2-norm condition number below 25.
- Derived parameter/frequency/reference arrays do not share source storage;
  mutating them, derived comments/warnings and mapping does not mutate source
  values, source metadata or caller-supplied names. Existing warnings persist.
- Invalid partitions, bool/noninteger indices, duplicate/empty names,
  unequal-within-pair/complex/nonpositive/nonfinite references, malformed
  matrices and invalid grids fail. Early partition/shape failures are checked
  before any S conversion call.
- 32,769 two-port samples execute, including first/last numerical checks;
  32,770 samples reject. 65 ports and empty/nonsquare samples reject.
- Exactly 4,194,304 entries (1024 x 64 x 64) reach conversion admission;
  4,198,400 entries (1025 x 64 x 64) reject before conversion. These two
  probes use a scalar broadcast view and intercept conversion before dense
  allocation. This is cap-admission evidence, not a full-size performance run.

All numerical comparisons use absolute tolerance `3e-14` and relative
tolerance `3e-13`; zero entries are protected by the absolute bound. Original
unit modal excitations fix the power scale at one watt. A separate executed
probe across all 63 port counts measured maximum absolute S error
`2.8017932319033294e-16` and net-power error `1.7763568394002505e-15` W.
The orthogonal real-reference basis change has condition number one. The
allowance covers finite precision V/I reconstruction and accumulation through
64 ports, with explicit conditioning admission for the independent circuit
solve. This algebraic change of coordinates has no mesh, iterative solver or
continuum convergence parameter; additional port counts are coverage, not a
convergence claim.

## Limits

These are supplied synthetic finite samples with real references equal within
each pair. DC denotes a supplied algebraic endpoint; the waveguide paper does
not establish DC field validity. There is no inference of broadband causality,
measured accuracy, fixture calibration, passivity repair, complex-reference
support, automatic pair discovery or physical device qualification. The
parent campaign retains integrated capture/reload and file-format evidence.
Full-suite, native/build and real-measurement checks were not run for this
bounded resource-constrained increment. Knowledgeable human numerical review
before release and all external/release gates remain required.
