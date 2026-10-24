<!-- SPDX-License-Identifier: Apache-2.0 -->
# Bounded generic PAM3 numerical path

Status: experimental source capability, reviewed 23 October 2026. This module
implements a finite-record three-level PAM precheck over an explicitly supplied
sampled linear channel. It is not a USB4 encoder or receiver, has no standard
mask or generation-specific limit, and makes no interoperability or compliance
claim. Knowledgeable human SI/numerical review and physical validation remain
required before release qualification.

The numerical owner is `python/spike_core/si_pam3.py`. The existing protocol
suite runner is intentionally unchanged: a generic three-level calculation does
not make its USB4 PAM3 stage executable or compliant. Worker method
`simulate_si_pam3` accepts exactly `{request: ...}` with contract
`spike/si-pam3-request/v1`, integer symbol indices 0/1/2, three strictly
increasing `levels_v`, `channel_impulse`, `symbol_rate_hz` and `samples_per_ui`.
Optional sampling/cursor, thresholds and noise controls follow the API below.
The self-contained schema is registered in `schemas/manifest.json`; semantic
and resource admission remain in the decoder/kernel. Unknown fields and native
execution controls fail. This route preserves the protocol runner's PAM3 guard.
Run [the original worker example](../examples/si/pam3-generic-worker.json).

## Public API and units

```python
from python.spike_core.si_pam3 import pam3_eye, ternary_test_symbols

symbols = ternary_test_symbols(1024, seed=7)
result = pam3_eye(
    symbols,
    symbol_to_level_v={0: -0.4, 1: 0.0, 2: 0.4},
    channel_impulse=[1.0],
    symbol_rate_hz=20.0e9,
    samples_per_ui=8,
    sampling_phase_ui=0.5,
    voltage_noise_rms_v=0.01,
    noise_seed=11,
)
```

`symbols` is an arbitrary sequence over exactly three integer or string labels.
`symbol_to_level_v` explicitly maps those labels to three distinct voltages.
`ternary_test_symbols` is a reproducible PCG64 engineering stimulus that always
exercises all levels; it is not a ternary PRBS definition, line code, scrambler,
training sequence, or protocol encoder.

`channel_impulse` is a real causal discrete-time voltage transfer. Its
coefficients have units V/V and are sampled at

`delta_t = 1 / (symbol_rate_hz * samples_per_ui)` seconds.

The source pulse is a rectangular zero-order hold. The FIR cursor defaults to
the largest-magnitude tap and may instead be supplied explicitly as
`channel_cursor_samples`. That index is an alignment choice, not clock recovery.
The sampling phase is fixed and dimensionless in `[0, 1)` UI. Optional noise is
iid zero-mean Gaussian voltage noise with the supplied RMS in volts and an
explicit 64-bit seed. Decision thresholds, when supplied, are volts.

The result contract is `spike/si-pam3-eye/v1`. It reports the ordered symbol and
voltage mapping, sample clock, FIR support, exactly two vertical eye openings,
thresholds, class statistics, a 3 by 3 confusion matrix, one finite seeded
observed symbol-error rate (SER), and the conditional Gaussian expected SER.
Status remains `experimental`, `production_qualified` is false, and compliance
is `not_evaluated`.

## Governing model and independent derivation

Let the three labels map to strictly ordered voltages
`a_0 < a_1 < a_2` in volts. For `S` samples/UI and symbol rank `r_k`, the
rectangular source is

`x[n] = a_(r_k),  k*S <= n < (k+1)*S`.

For an explicitly supplied causal real FIR `h[m]`, the received noiseless sample
stream is the discrete LTI convolution

`y[n] = sum_(m=0)^(L-1) h[m] x[n-m]`.

This is evaluated by SPIKE's existing bounded NumPy FFT convolution hot path.
NumPy FFT is already compiled code; no new C++ kernel is justified without an
equal-error end-to-end profile. The decision sample for source symbol `k` is
linearly interpolated at

`n_k = k*S + c + phi*S`,

where `c` is the declared cursor index and `phi` is the fixed phase in UI. A
symbol is retained only when its sample has the full declared FIR history and
does not use a zero-padded future beyond the finite source record. This makes
identity, FIR and pure-delay oracles unambiguous and prevents constant endpoint
extension from manufacturing observations.

For thresholds `t_0 < t_1`, the memoryless receiver decides ranks 0, 1 and 2 in
the intervals `[-infinity,t_0)`, `[t_0,t_1)` and `[t_1,+infinity)`. If thresholds
are omitted, they are midpoints between the three retained noiseless class
means. This is explicitly a training-mean, equal-prior nearest-mean choice, not
an adaptive receiver or a protocol threshold rule. If the class means are not
strictly increasing, inference fails instead of silently correcting polarity or
falling back to an NRZ/PAM4 implementation.

For the adjacent source ranks `i` and `i+1`, the deterministic eye opening is

`H_i = min(y_k | r_k=i+1) - max(y_k | r_k=i)`, for `i=0,1`.

Thus a negative height honestly records a closed eye. The threshold margin is
the smaller distance from the threshold to those two worst-case boundaries; it
may also be negative.

For each retained sample, a seeded draw `e_k ~ Normal(0,sigma^2)` gives
`v_k = y_k + e_k`. Hard decisions on `v_k` produce an observed error count and
SER. This is an actual finite experiment, not a Gaussian level-separation proxy.
It is still only one synthetic realization and cannot demonstrate a rare-event
rate.

The second statistic integrates the same stated additive-noise model instead of
depending on seed length. With standard normal CDF `Phi`, its conditional error
probabilities are

- rank 0: `1 - Phi((t_0-y_k)/sigma)`;
- rank 1: `Phi((t_0-y_k)/sigma) + 1 - Phi((t_1-y_k)/sigma)`;
- rank 2: `Phi((t_1-y_k)/sigma)`.

Their arithmetic mean over the actual retained deterministic record is the
reported `expected_symbol_error_rate_gaussian`. At zero noise it is the exact
deterministic threshold-error fraction. This calculation retains deterministic
ISI sample by sample; it does not replace each class with a fitted Gaussian,
extrapolate FEC, or imply independent channel errors.

## Mathematical sources actually reviewed

These sources informed the equations only. No external implementation, example,
waveform, fixture, prose, or standards table was copied.

- H. Nyquist, "Certain Topics in Telegraph Transmission Theory," *Transactions
  of the AIEE*, volume 47, 1928, pages 617-644; reprinted in *Proceedings of the
  IEEE* 90(2), 2002, pages 280-305, DOI
  [10.1109/5.989875](https://doi.org/10.1109/5.989875). Reviewed reprint pages
  281 and 287-293: finite signaling conditions, overlapping pulse contributions,
  middle-of-unit observations, and interference between distinguishable current
  values. This is a general signaling foundation, not a current protocol limit.
- R. Gallager, *Principles of Digital Communication*, MIT 6.450 course notes,
  2006, [chapter 6](https://ocw.mit.edu/courses/6-450-principles-of-digital-communications-i-fall-2006/1e8d60eb6c0a68cc48e81af039fd4af6_book_6.pdf),
  section 6.2 and equations (6.3), (6.5), (6.8)-(6.10), pages 169-175. Reviewed
  the real-valued PAM alphabet, shifted-pulse waveform, additive Gaussian sample
  model, filter convolution, T-spaced sampling and ISI definition.
- R. Gallager, same notes,
  [chapter 8](https://ocw.mit.edu/courses/6-450-principles-of-digital-communications-i-fall-2006/f6c75b427b022503f5c605db7de4d46f_book_8.pdf),
  sections 8.3.2 and 8.4.1-8.4.2, equations (8.26), (8.38) and (8.40)-(8.42),
  pages 256-267. Reviewed midpoint/minimum-distance decisions under equal-prior
  Gaussian noise and arbitrary M-ary decision regions. SPIKE's user-supplied
  thresholds may deliberately differ, so the code integrates their exact three
  regions rather than claiming they are maximum-likelihood.
- NIST/SEMATECH, *e-Handbook of Statistical Methods*,
  [section 1.3.6.6.1, Normal Distribution](https://itl.nist.gov/div898/handbook/eda/section3/eda3661.htm),
  reviewed 23 October 2026: normal density, standard deviation and CDF definition.
  This supports the stated synthetic Gaussian-noise integral, not a claim that
  real receiver noise is Gaussian.
- USB-IF, "USB-IF Announces Publication of New USB4 Specification to Enable USB
  80Gbps Performance," 18 October 2022,
  [page 1](https://www.usb.org/sites/default/files/2022-10/USB-IF%20USB%2080Gbps%20Announcement_FINAL_v2.pdf),
  reviewed only for the public fact that the architecture uses PAM3 signaling.
  No normative encoding, training, electrical limit, mask, or compliance rule
  was reviewed or implemented. The separately listed USB4 v2 specification has
  use and licensing terms and is not source material for this generic kernel.

## Numerical analysis and bounds

| Item | Admission or behavior |
| --- | --- |
| Symbol record | 64 through 16,384 symbols; every level must have at least eight retained observations |
| Voltage levels | three distinct finite levels in `[-1000, 1000]` V; total span at least `1e-15` V |
| Symbol rate | finite `1` through `1e12` symbols/s |
| Sampling | integer 8 through 256 samples/UI; at most 1,048,576 source samples |
| FIR | 1 through 65,536 finite real causal taps; nonzero; L1 gain at most `1e6` |
| FFT | next power-of-two convolution allocation at most 2,097,152 points |
| Thresholds | two increasing finite voltages, each within `+/-1e9` V |
| Noise | finite RMS `0` through `1000` V; seed from 0 through `2^64-1` |
| Cancellation | checked before allocation and after convolution; no in-FFT cancellation |

The L1 channel bound and level bound cap the noiseless convolution magnitude;
finite input checks reject NaN, infinity, complex taps, collapsed mappings and
zero channels. FFT convolution has ordinary floating-point roundoff. Fractional
decision positions use linear interpolation on the declared sample grid; no
claim is made about continuous-time accuracy between those samples. There is no
automatic resampling, DC synthesis, windowing, de-embedding, passivity repair or
causality repair.

An upstream sampled-network adapter may pass a FIR only after its own existing
uniform-grid and explicit-DC admission has produced a real causal voltage-domain
impulse at exactly the requested sample interval. A Touchstone/network record
without DC cannot be silently interpolated or given a synthetic DC point for
this route. Approximate, nonpassive, unvalidated or source-limited network status
must remain in the enclosing service provenance; the PAM3 result does not
upgrade it.

## Executed verification

`python -m unittest tests.python.test_si_pam3 -v` passed 13 tests on
23 October 2026. The independent checks cover:

- arbitrary string-label mapping through an analytical identity channel, both
  exact eyes, midpoint thresholds and a diagonal confusion matrix;
- a hand-computed symbol-spaced two-tap FIR
  `y_k = 0.75*a_k + 0.25*a_(k-1)`;
- an integer-sample pure delay with bounded retained support and no endpoint
  extension;
- deliberately bad explicit thresholds producing the exact 2/3 SER and expected
  confusion matrix;
- the balanced identity/AWGN result `SER = 4*Q(0.5/sigma)/3` at `sigma=0.2 V`;
- the same analytical SER at `sigma=0.05 V`, checked by relative error so direct
  Gaussian survival evaluation is required and `1-Phi(z)` cancellation cannot
  erase the approximately `1e-23` result;
- identical seeds producing identical float64 sample digests and different seeds
  producing different digests;
- malformed mappings, unknown labels, nonfinite/complex/zero channels, inverted
  threshold order, phase and waveform resource rejection, inadequate per-level
  populations, inverted inferred means, and cooperative cancellation.

These are code and solution verification cases. They are not measured physical
validation, Touchstone conversion validation, hardware qualification, protocol
conformance, or a performance benchmark. No native speedup is claimed.

## Exact limitations and integration boundary

- Only three real voltage levels, rectangular pulses, a causal sampled LTI FIR,
  fixed-phase sampling, two memoryless thresholds and optional iid Gaussian
  decision-sample noise are modeled.
- There is no USB4 bit/symbol mapping, scrambler, precoder, training, lane state,
  transmitter/receiver electrical model, CTLE/FFE/DFE, CDR, jitter, crosstalk,
  nonlinear/noise coloring, FEC, mask, normative limit or compliance decision.
- The training-mean thresholds use this same finite record and are optimistic as
  a receiver setup. Supply explicit thresholds when independent values exist.
- The Gaussian expected SER is conditional on the supplied model and finite
  deterministic sequence. The seeded observed SER has finite-trial uncertainty.
- The FIR must already represent the desired launched/received voltage boundary
  and sample clock. Its construction and physical validity remain upstream.
- No NRZ or PAM4 numerical path is called as a fallback.

Clean-room statement: the derivation, implementation, tests and prose are
original SPIKE work based only on the cited mathematical sources and official
public metadata. No third-party source code, examples, test vectors, normative
tables or proprietary standard text were used.
