<!-- SPDX-License-Identifier: Apache-2.0 -->

# Internal SPICE SIN Source Slice

SPIKES accepts the bounded independent-source form
`SIN(VO VA FREQ [TD [THETA [PHASE]]])` when native extensions are enabled.
`VO` and `VA` use the source unit, `FREQ` is in hertz, `TD` is in seconds,
`THETA` is in inverse seconds, and `PHASE` is in degrees. Frequency is
required and positive. Delay and damping must be nonnegative. The three
trailing values default to zero.

For time `t < TD`, the value is `VO`. At and after the delay, SPIKES uses

```text
VO + VA * exp(-THETA * (t - TD))
        * sin(2 * pi * FREQ * (t - TD) + PHASE * pi / 180)
```

This matches the source equation and parameter meanings in the
[ngspice user manual, section 4.1.2](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).
The implementation was independently authored from that published equation;
no ngspice source code, test data, or implementation text was used.

The Python reference MNA evaluates the equation at every fixed transient
sample. The owned C++ route receives a PWL lowering sampled on the requested
`.tran` grid, so source values are exact at returned sample times and linear
between them. This is a fixed-step compatibility slice, not a claim of full
ngspice source parity. Every generated PWL sample is a breakpoint and may make
hybrid integration select backward Euler, so this route does not claim the
same smooth-source integration history as ngspice. In particular, the ngspice
default `FREQ=1/TSTOP` when frequency is omitted is not accepted, adaptive
between-sample sine resolution is not implemented, and `EXP`, `SFFM`, AM, and
random-source forms remain unsupported. Choose a time step that resolves the
highest source frequency and check reactive results under step refinement.

Regression coverage checks parser and JSON round trips, optional defaults,
strict rejection, delay/damping/phase values against the closed-form equation,
and the owned native C ABI when a test library is provided through
`SPIKES_TEST_NATIVE_LIBRARY`.
