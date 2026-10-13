# Internal SPICE analytic source waveforms

## Scope

The native-extension netlist route accepts bounded `SIN`, `EXP`, and `SFFM`
independent voltage and current sources. This is a narrow source-language slice,
not a claim of full SPICE or ngspice compatibility. The ordinary parser route
continues to require explicit opt-in before accepting these native extensions.

The Python reference MNA engine evaluates each analytic source directly. The
owned C++ ABI evaluates SIN directly at each internal solve time, including
adaptive substeps, and forces a solve at its delay boundary. Persistent
sessions retain global source time and checkpoint replay. Older ABI-v1 libraries
without the additive SIN symbols fail explicitly; there is no sampled fallback.
The native runner still lowers EXP and SFFM to PWL values on the requested fixed
`.tran TSTEP TSTOP` grid. The allocator rejects grids above 1,000,000 samples
before creating the time tuple. Values between requested output samples have
PWL interpolation semantics; adaptive breakpoints and ngspice internal source
breakpoint behavior for EXP/SFFM are outside this slice. Retained native output
can be linearly resampled from solve points; direct source evaluation does not
make an arbitrary output interpolation exact. See the
[native SIN checkpoint and remaining gates](validation/NATIVE_SIN_PARITY_2026-10-12.md).

## Accepted forms and equations

`SIN(VO VA FREQ [TD [THETA [PHASE]]])` requires an explicit positive frequency;
omitted delay, damping and phase are zero. Delay and damping must be nonnegative.
With `u = max(0, t-TD)` and phase in degrees, the equation is
`VO + VA * exp(-THETA*u) * sin(2*pi*FREQ*u + PHASE*pi/180)`.
Before delay, the phase-dependent initial value is held; it is not necessarily
VO. This corrects the earlier SPIKE phase-before-delay discrepancy.

The additive C ABI functions `spikes_circuit_add_sine_voltage_source` and
`spikes_circuit_add_sine_current_source` accept those six values in that order.
`NativeCircuit.add_sine_voltage_source` / `add_sine_current_source` accept a
six-value tuple. `native-run` uses these owned primitives automatically.
SIN has no PWL allocation proportional to the output-grid size. Solver work
limits still apply. Users must choose a maximum step that resolves the signal;
the embedded storage-defect estimator is not an anti-aliasing guarantee.

`EXP(V1 V2 TD1 TAU1 TD2 TAU2)` requires all six values. SPIKE deliberately
does not accept the ngspice omitted-parameter defaults because `TAU1`, `TD2`,
and `TAU2` then depend on transient-analysis settings. Delays must be
nonnegative and ordered (`TD2 >= TD1`); both time constants must be positive.
With `A = V2 - V1`, SPIKE evaluates:

```text
t < TD1:          V1
TD1 <= t < TD2:   V1 + A * (1 - exp(-(t - TD1) / TAU1))
t >= TD2:         V1 + A * (1 - exp(-(t - TD1) / TAU1))
                     - A * (1 - exp(-(t - TD2) / TAU2))
```

`SFFM(VO VA FC MDI FM [TD [PHASEM [PHASEC]]])` accepts five through eight
values. This supports the traditional five-value form and the current ngspice
form; omitted delay and phases are zero. Frequencies must be positive, delay
must be nonnegative, and the documented bound `0 <= MDI <= FC/FM` is enforced.
For `t > TD`, phases in degrees are converted to radians and SPIKE evaluates:

```text
VO + VA * sin(2*pi*FC*(t-TD)
              + MDI*sin(2*pi*FM*(t-TD) + PHASEM)
              + PHASEC)
```

At and before `TD`, SFFM returns zero, matching the current manual equation's
stated boundary. This may differ from other SPICE-family dialects. Default
carrier or modulating frequencies derived from `TSTOP` are not supported.

## Evidence and validity limits

The equations and parameter meanings were independently implemented from the
[ngspice user manual, chapter 4.1](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf),
sections 4.1.3 and 4.1.5. No upstream implementation source was consulted or
adapted. The code, fixtures, oracle equations, and prose are independently
authored for SPIKE under its existing Apache-2.0 boundary.

`tests/python/test_spikes_exp_sffm_source.py` checks parser round trips,
malformed and unsafe input rejection, direct Python evaluation against separate
equations at every requested sample, execution through the specified owned
`spikes_c_api.dll`, and backward-Euler step refinement against a closed-form
EXP-driven RC response. These checks qualify only the documented fixed-grid,
linear source behavior. They do not qualify omitted ngspice defaults, adaptive
time stepping, source breakpoints, nonlinear devices, or full dialect parity.
