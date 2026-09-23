# Static Q/M bindings and native transient FRA

Development source update; installed beta.5 is unchanged.

## Strict semiconductor subset

```
.model qm NPN(IS=1f BF=99 BR=1 NF=1)
Q1 collector base emitter qm
.model mm NMOS(LEVEL=1 VTO=1 KP=1m LAMBDA=0 GAMMA=0 PHI=.6)
M1 drain gate source bulk mm W=2u L=1u
```

These connect to the existing C++ Ebers–Moll NPN and Level-1 NMOS functions.
Scoped models, hierarchy and parameter expressions are resolved by the existing
frontend. Unknown model parameters, PNP/PMOS, BSIM levels and non-27°C operation are
not supported by this binding. BF/BR convert to alpha=beta/(beta+1). Model parameters
are retained in normalized project serialization. MOS defaults to W/L=1 if omitted.

Source update: BE/BDF2 now support the explicit bounded charge terms documented in
NATIVE_TRANSISTOR_CHARGE.md, along with SPK_GAN/SPK_SIC bindings. Hybrid trapezoidal
still rejects the Q/M charge path; vendor accuracy is not implied.
Device models must be extended and qualified before enabling those features. The
schematic keeps its primary output terminals first, followed by control/body pins;
it is not yet a qualified manufacturer symbol/package mapping.

## Native sine-injection FRA

```
python -m python.spikes transient-fra circuit.cir --library path/to/spikes_c_api.dll --source Vinject --output-probe "V(out)" --frequency-hz 1000 --frequency-hz 2000 --amplitude .01 --max-step-s 1e-6 -o response.json
```

Place an explicit independent DC voltage source at the desired injection point.
The experiment adds a sine around its DC value, retains the circuit's other switching
sources, runs independent native backward-Euler transients, discards eight excitation
cycles, and fits the fundamental over four cycles using time-weighted least squares.
Frequency, complex response, dB/phase and nonfundamental residual RMS are reported.
The residual includes switching content and is NOT a THD measurement.

The user must choose a timestep that resolves both the carrier and relevant circuit
time constants. At least 64 points per excitation cycle are used; each experiment
is capped at 100,000 nominal samples and a sweep at 100 frequencies. Smaller steps
can alter measured phase and gain; convergence studies are still required. Settling
is assumed, not automatically proven. No phase/gain margin is inferred automatically.

This is a sampled transfer experiment, not a periodic operating-point linearizer or
a general closed-loop return-ratio extraction method. No C-controller attachment,
automatic loop fixture, state hand-off between frequencies, hardware FRA or physical
HIL certification is supplied. Arbitrary nonlinear native B expressions, detailed
BSIM/IGBT/thyristor/WBG netlist integration and manufacturer qualification remain open.
