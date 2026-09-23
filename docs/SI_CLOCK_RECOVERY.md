<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Bounded NRZ clock recovery

`python/spike_core/si_clock_recovery.py` implements an approximate behavioral
threshold-transition timing detector and proportional/integral (PI) clock.
It is dynamic feedback, not a best-phase scan or an ideal transmitted clock.
It is not Gardner, a transistor-level CDR, a recent research novelty, or a
qualified implementation of any communications interface.

## API and workflow

`validate_cdr_model(model)` returns a normalized `CdrModel` typed dictionary.
`recover_nrz_clock(times, voltage, nominal_rate_hz, model)` accepts full-resolution
real 1-D arrays in seconds and volts. The caller must supply the original
waveform before plot decimation. At least four samples per nominal unit interval
(UI) at every time gap are required; this gate alone cannot detect prior
decimation. The loaded SI workflow's existing eight-samples/UI gate remains.
Set the receiver's optional `cdr` object to opt in. Original fixed-clock eye
measurements and CDR outputs remain separate; recovery does not retroactively
validate eye, jitter, BER, or interface-compliance claims.

Options (unknown keys are rejected):

| Key | Default | Admission |
| --- | --- | --- |
| `kind` | `transition_pi` | Only this method |
| `threshold_v` | 0.5 | Finite volts; user chooses received crossing level |
| `normalization_v` | 1 | 1e-12 through 1e12 V, positive amplitude scale |
| `initial_phase_ui` | 0 | 0 inclusive to 1 exclusive; boundary phase relative to record start |
| `proportional_gain` | 0.2 | Greater than 0 through 0.5 |
| `integral_gain` | 0.002 | Greater than 0 through proportional gain divided by 4 |
| `max_frequency_offset_ppm` | 10000 | Greater than 0 through 100000 |
| `max_symbols` | 65536 | Integer 1 through 65536 |

Choose the threshold for the **received** waveform, not the source open-circuit
levels. A matched 0--1 V source can arrive as approximately 0--0.5 V; a 0.5 V
threshold would then provide no useful timing information. No automatic eye
optimization or rail estimation is performed. Normalization must not overflow.

Outputs include center `sample_times_s`, `sample_values_v`, the integrator's
`period_s` and `frequency_offset_ppm` history, accepted `transition_times_s` and
pre-correction `phase_error_ui`, detector counts, diagnostics, and normalized
model. Histories are NumPy arrays, not serialized transport objects.
`status: tracking` means only that at least eight transitions drove updates;
otherwise it is `insufficient_transitions`. Neither status is a lock decision.
All results retain `model_status: approximate`.

## Independent derivation

Use dimensionless time `x = (t - t[0])/T0`, with nominal period `T0 = 1/rate`,
and voltage `u = (v - threshold)/normalization`. For a sign change between
adjacent samples, solve their straight-line interpolation for `u=0`. With
`a=abs(u_left)` and `b=abs(u_right)`, the fractional crossing location is
`a/(a+b)`. The implementation divides both amplitudes by `max(a,b)` before
forming this ratio to avoid overflow. A threshold sample belongs to the upper
half-plane; a monotone exact-threshold crossing is counted once.

At predicted boundary `B`, search a gate of `B +/- 0.45*P`, where `P` is the
current period in nominal UI. Exactly one crossing provides timing error
`e = crossing - B`. Multiple crossings are ambiguous and skipped. No crossing
means holdover with the existing period. Already consumed crossings cannot
drive a later update. On an accepted event:

```
P_new = clip(P + Ki*e, 1/(1+d), 1/(1-d))
B_corrected = B + Kp*e
sample_center = B_corrected + P_new/2
B_next = B_corrected + P_new
```

Here `d = max_frequency_offset_ppm*1e-6`. Period bounds correspond exactly to
oscillator **frequency** offsets, not approximate equal-and-opposite period
offsets. Reported frequency is `(T0/period_s - 1)*1e6`. The proportional phase
correction also changes consecutive sample spacing; the frequency bound applies
to the integrator state, not to every instantaneous intersample interval.

For exact one-transition-per-UI observations and no clipping, let `e` denote
boundary error and `p=P-P_true` period error. The next errors are
`e_next=(1-Kp-Ki)*e-p` and `p_next=p+Ki*e`. The linear update matrix has trace
`2-Kp-Ki` and determinant `1-Kp`. Its unit-circle stability conditions include
`Kp>0`, `Ki>0`, and `2*Kp+Ki<4`; the admitted gains satisfy these. This is a
local, transition-rich result, not a global lock guarantee. Missing transitions,
cycle slips, ambiguous edges and clipping invalidate that simple linear model.

The method is independently derived from interpolated threshold locations and
a two-state feedback recurrence. No external source code, prose, fixtures or
implementation was examined or adapted. The recent papers in
[the research roadmap](SERDES_ACTUATOR_DELIVERY.md) are candidates, not sources
for this algorithm or validation evidence.

## Conditioning, bounds and limitations

Time is translated to the record origin before UI normalization. Input samples
must be finite, time strictly increasing, and rate 1e-6 through 1e15 Hz. At
most 1,048,576 input points and the configured output symbol count are admitted;
excess is an explicit error, never silently truncated. Storage is O(input
samples + output symbols); each symbol uses two binary searches over crossings.
The surrounding worker owns process timeout/cancellation and transport limits.

Only centers within the supplied record are emitted. Linear interpolation
never extrapolates at either end. Detection is an offline bounded-window
operation with up to 0.45 period lookahead, not a claim of streaming causality.
Flat data free-runs and cannot establish timing. The detector has no hysteresis;
noise, flat threshold plateaus, severe ISI and multiple threshold crossings can
make timing unavailable or biased. Asymmetric edges lock to threshold crossing,
not necessarily the optimum eye center. Initial phase outside a usable capture
gate, long transition-free runs, or excessive rate mismatch can prevent
acquisition or cause cycle slips. No adaptation, CDR jitter-transfer compliance,
PAM4, BASE-T modulation, equalizer coupling, random-noise injection, measured
device correlation or production qualification is implied.

## Reproducible evidence

Run:

```
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_si_clock_recovery -v
```

Eleven tests use independently constructed finite-edge piecewise-linear NRZ and
smooth cubic edges with analytical crossing and ideal-center locations. They
do not use the production NRZ source helper as an oracle. Coverage includes
both signs of 4000 ppm offset, 0.23 UI initial error, a -2000 to +2000 ppm
frequency ramp, grid convergence at 8/16/32/64 samples/UI, no-transition and
ambiguous-crossing records, threshold/amplitude invariance, record-origin
translation, bounded frequency state, invalid options/arrays and resource gates.

In the deterministic 3000-symbol, 32-samples/UI +4000 ppm fixture, center error
RMS decreases from 0.083779 UI over the first 32 samples to less than 1e-5 UI
over the last 500 (observed approximately 6.6e-13 UI for exact linear edges).
This near-roundoff result is specific to noiseless exactly linear interpolation,
not an accuracy claim for physical receivers. In the frequency-ramp fixture,
last-500 center error RMS is approximately 0.001317 UI versus 0.296768 UI for
the unchanged nominal clock. Smooth-edge refinement must improve monotonically
and finish below 1e-4 UI. These are bounded numerical regressions; knowledgeable
human numerical review and independent measured qualification remain required
before release.
