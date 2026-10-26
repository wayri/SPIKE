<!-- SPDX-License-Identifier: Apache-2.0 -->

# SI08-I02 independent causality-policy witnesses

Date: 25 October 2026. This bounded increment exercises the unchanged
`sparameter_sampling.py` and `sparameter_rational.py` owners through
`tests/python/test_si08_causality_policy_oracles.py`. It supplies independent
analytical causal and deliberately anti-causal witnesses, actual interpolation
refinement, explicit DC cases and a finite-grid ambiguity counterexample.
No new physics or causality-detection kernel is introduced.

## Primary sources and provenance

Reviewed on 25 October 2026:

- A. V. Oppenheim and G. C. Verghese, *Signals, Systems and Inference*, MIT
  6.011 class notes, Spring 2010,
  [author/institution original](https://ocw.mit.edu/courses/6-011-introduction-to-communication-control-and-signal-processing-spring-2010/a6bddaee5966f6e73450e6fe79ab0566_MIT6_011S10_notes.pdf).
  Section 2.2.1, printed pp. 25-26: LTI causality and impulse support;
  section 2.2.2, equations (2.9) and (2.11), pp. 26-27: bilateral Laplace
  and negative-sign Fourier conventions; section 3.1, Example 3.1,
  equation (3.3), p. 48: linear phase for delay/advance. Reviewed text extraction.
- [NIST DLMF section 1.14](https://dlmf.nist.gov/1.14), equations
  [1.14.1](https://dlmf.nist.gov/1.14.E1) and
  [1.14.17](https://dlmf.nist.gov/1.14.E17), live mathematical edition
  consulted on the review date: Fourier and unilateral Laplace definitions.
  DLMF's Fourier definition uses a positive sign and a `1/sqrt(2*pi)` factor.
  The present convention is explicitly `H(omega)=sqrt(2*pi)*F_DLMF(-omega)`;
  no sign or normalization is silently transferred.

All derivations, synthetic values, code and test oracles are original SPIKE
work under Apache-2.0. No external implementation, example corpus, measured
trace, inverse-transform program or vendor fixture was inspected or adapted.
The references provide definitions; they do not qualify these synthetic data.

## Independent support and transform derivation

Use `H(j*omega)=integral h(t)*exp(-j*omega*t) dt`, `omega=2*pi*f`.
Frequency f is Hz, time t is seconds, omega and decay/pole rates have units
rad/s or inverse seconds as appropriate, dimensionless S/H relates normalized
waves, and the impulse h has units inverse seconds. These are scalar LTI
transfer witnesses, not an electromagnetic field extraction.

For delay tau > 0, `h(t)=A*delta(t-tau)` gives
`H(j*omega)=A*exp(-j*omega*tau)` and support at positive time. Replacing tau
by -tau places support before zero and changes the phase sign. These
supports are known from construction, not inferred from samples.

Define a damped resonant witness with `a=2*pi*40e6`, `b=4a`, `g=0.2`:

```text
K = g*(a*a+b*b)
h(t) = (K/b)*exp(-a*t)*sin(b*t), t >= 0; zero otherwise
H(s) = K / ((s+a)^2+b^2)
```

Expand sine as two exponentials and integrate each over positive time:
the difference of `1/(s+a-j*b)` and `1/(s+a+j*b)`, scaled by `K/(2j*b)`,
reduces to the displayed rational expression. Poles are `-a +/- j*b`.
For the reversed impulse `h_rev(t)=h(-t)`, substituting u=-t in the Fourier
integral gives `H_rev(j*omega)=H(-j*omega)=conj(H(j*omega))` because h is real.
It is nonzero at a selected negative time despite identical response
magnitudes. Its bilateral transform has a left-half-plane region of
convergence `Re(s)<a`, so a positive-real-part pole expression here must not
be interpreted as a stable causal realization.

For a delayed resonance, substituting u=t-tau gives the extra factor
`exp(-j*omega*tau)` and support t>=tau. Independent numerical quadrature
checks the resonance and delayed-resonance transforms, with phase evaluated
inside the integral. Integration uses dimensionless u=a*t, interval [0,40],
and absolute/relative quadrature targets `2e-13`. The omitted tail is at
most `K/(a*b)*exp(-40) < 4e-18`; comparison tolerance is `2e-12`.
These checks confirm transform sign and scale without using a production
frequency basis or fitting a complex-pole model.

## Interpolation derivation and actual refinement

For interval width df and midpoint fm, averaging the two delay endpoints
gives `A*exp(-j*2*pi*fm*tau)*cos(pi*df*tau)`. Hence the exact complex error
is `A*(1-cos(pi*df*tau))`, quadratic as df tends to zero.

For resonance, the same partial fractions yield a global second-derivative
bound with respect to Hz:
`M2=2*K*(2*pi)^2/(b*a^3)`. Each denominator has magnitude at least a on the
real-frequency axis. Applying the integrated second-derivative remainder
on each interval gives midpoint interpolation error at most `M2*df^2/8`.
This is a bound for this explicit analytical witness, not arbitrary data.

The tests call the real Cartesian interpolation owner at every refinement;
source grids are genuinely resampled from the analytical responses.

| Original witness | Source intervals | Actual maximum complex errors |
| --- | --- | --- |
| A=0.72, tau=0.6 ns delay, 0..4 GHz | 16, 32, 64, 128 | 0.0784753025844, 0.0198936573137, 0.00499071099245, 0.00124876066700 |
| Resonance above, 0..320 MHz | 64, 128, 256, 512 | 0.00164576707989, 0.000414380571590, 0.000103776766662, 0.0000259550688178 |

Delay refinement ratios are 3.94474, 3.98614, 3.99653; resonant ratios are
3.97163, 3.99300, 3.99832. Delay errors agree with the exact formula within
`5e-15`; resonant errors obey the curvature bound. Test acceptance requires
delay ratios in (3.9,4.01), resonant ratios in (3.8,4.1), and final errors
below 0.0013 and 0.00003 respectively. At most 513 source samples are used,
within the existing 4096-sample cap. These numerical tolerances and frequency
domains are explicit fixture contracts. Grid refinement does not establish
source causality, out-of-band accuracy or time-domain reconstruction validity.

## Exact finite-grid ambiguity and constructed-model distinction

Let `f_k=k*df`, `df=100 MHz`, `tau=1/(4*df)` and `advance=3/(4*df)`.
Then `tau+advance=1/df`; the delay and advance frequency responses differ by
`exp(j*2*pi*k)=1` at every supplied sample. The tests use exact rational
quarter-cycle arithmetic and records cycling through `0.7*[1,-j,-1,j]`.
Direct high-cycle floating exponentials initially showed avoidable phase
roundoff; reducing exact rational cycles before exponentiation corrects the
oracle without relaxing acceptance tolerances. The production inputs remain
ordinary finite JSON scalar records.

Both physical constructions therefore supply identical 17-point data. The
resampler returns identical interpolated arrays and retains its limitation
against causality qualification. At intervening midpoints the exact delay
and advance responses are opposite, differing by 1.4. This explicit
counterexample rules out certainty about support from these finite samples.

A second ambiguity uses advance `1/df`: every supplied sample is exactly
0.7, which the existing stable proper real-pole fitter reproduces using
direct term 0.7 and zero residue. The fitted realization is causal by
construction, while the sampled source could have negative-time support.
The test retains `proper_real_rational_by_construction` only for the model,
and requires the existing source-causality limitation. Conversely, a chosen
real-pole fit of reversed first-order data fails its sample-error limit;
that error is not treated as a general noncausality detector.

## Executed acceptance and limits

All nine oracle tests pass in the existing interpreter:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv-emerge3/Scripts/python.exe -B -m unittest tests.python.test_si08_causality_policy_oracles -v
```

The corpus also executes missing DC rejection when zero is requested,
positive-only support without inventing DC, explicitly supplied real DC,
retained source DC, rejection of imaginary DC and attempted replacement,
source snapshot preservation, and conjugate interpolation of anti-causal
witnesses. All sampled norms in those causal/reversed examples remain below
one, demonstrating that this diagnostic does not establish support.

The integrated parent report supplies the explicit
`source_causality: unknown_from_finite_samples` interpretation independently
of its optional constructed-model classification. The unchanged numerical
owners retain that distinction through existing limitations. The parent
campaign owns report transport and its source-bound combined receipt.

This evidence meets the frozen I02 analytical witness/refinement/policy scope;
it does not implement arbitrary noncausality detection, passive causal model
repair, complex-pole fitting, automatic DC inference or full SI08 qualification.
Full-suite/native/build checks and physical measurements were not run in this
bounded low-storage increment. External validation and knowledgeable human
numerical review before release remain separate required gates.
