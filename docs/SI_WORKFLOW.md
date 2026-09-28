# Source-to-receiver SI workflow

For a step-by-step Marble board context and executable four-port tutorial
covering S-parameters, reflection/VSWR, NEXT/FEXT, TDR/TDT, and eyes, see the
[SI user guide](SI_USER_GUIDE.md). Its analytical channel is explicitly
separate from the imported board.

Programmatic requests can opt into a receiver `cdr` object, as shown in
`examples/si/10g-nrz-cdr.json`. [Transition-PI recovery](SI_CLOCK_RECOVERY.md)
uses full-resolution loaded voltage before plot decimation. Choose thresholds
for received levels (including source/load division), not open-circuit source
levels. Recovered samples are separate from fixed-clock eye measurements;
`tracking` is a transition-count diagnostic, not lock or BER qualification.

Open **HF / SI → S-parameter workbench → Source-to-receiver workflow** in the
Tauri desktop. The original geometry/protocol workbench remains on the second
tab. The Python worker owns calculations and validates every study. Browser
preview supports configuration and saved-result visualization; execution uses
the desktop worker.

The **HF / SI** tab now selects SI setup and results in the main dock instead of
retaining PI solver controls and metrics. **NEXT / FEXT** opens the geometry
channel tab with a required separate victim net; the bounded solver reports
source-to-victim-near and source-to-victim-far transfer. **Ports** opens the
loaded workflow's source/receiver assignment page; these are channel ports,
not PI measurement probes. **Eye diagram** and **PAM4** open runnable geometry
channel settings with the corresponding modulation. Mesh and Solve with the SI
domain selected open the same SI workflow. Choose the exact signal, victim,
reference net and copper layer before running; no net pair is inferred as a
qualified crosstalk path.

With a single-ended aggressor and explicit victim selected, **Loaded NEXT /
FEXT voltage** enables a separate terminal-voltage calculation. Enter the
open-circuit Thevenin pulse amplitude and the four resistances in the displayed
port order: aggressor-near source, victim-near load, aggressor-far load, and
victim-far load. The pulse is a bounded 512-sample stimulus. Its sample interval
comes from the uniformly spaced frequency grid, so this mode requires DC and
at most 8,193 frequency points. The matched S-parameter NEXT/FEXT traces remain
separate from these loaded victim voltages.

When a completed geometry channel result is bound to the active canonical
design and both canonical net IDs, SPIKE's 3D board viewport highlights the
aggressor and victim routes. Click either route to identify it while reviewing
the board from another side. The NEXT/FEXT values shown beside those routes
are whole-channel transfer and loaded-terminal metrics; their route colors
are categorical and do not encode local coupling voltage. A raw KiCad layout
without a canonical DesignIR binding does not admit this overlay.

For an imported two-layer board, the **S-parameter solver** selector in the
**HF / SI** ribbon can route **S-parameters** and **Ports** to the optional
EMerge Suite extension. SPIKE enables that choice only after the trusted
extension's runtime probe reports `si_s_parameters`. The EMerge setup selects
explicit signal/return pads, frequency sweep, and mesh target; **Run** executes
its port sweep and shows the admitted S-parameter plots in SPIKE. These results
remain `unvalidated` as described in [Solver Status](SOLVER_STATUS.md).
Impedance, NEXT/FEXT, eye, PAM4, protocol suites, and Touchstone import keep
their existing SI paths because the EMerge adapter does not expose those
capabilities.

Opening a named protocol suite or channel profile selects the geometry/protocol
tab and its preset. Both loaded studies and geometry/protocol runs offer a
Stop action while their worker is active; worker failures restore the Run
action and retain their diagnostic. Browser preview disables worker execution
and IBIS inspection with an explanation. Setup imports are disabled during a
loaded run so its returned result remains associated with the submitted setup.
New source/receiver rows use unused channel ports, and network edit defaults
follow the known channel port count. A partial loaded result remains partial
in the completion message; inspect its blocked time-domain or export reason
before using that stage.

PAM4 finite-record analysis excludes symbols whose delayed sample falls beyond
the computed response. All phases use the same supported population and fewer
than 64 symbols fails explicitly; increase the source length when needed.
See [reliability notes](SI_FIELD_RELIABILITY_20260920.md). This does not change
the ideal-CDR, training-DFE or Gaussian-BER approximation limits.

## Study sequence

1. Choose a user-defined uniform RLGC line, import Touchstone, or select an
   active canonical board path and its explicit reference conductor. Coupled
   RLGC defaults to four ports: aggressor near, victim near, aggressor far,
   victim far. Board extraction retains the existing bounded geometry gates.
2. Assign source and receiver ports. Source voltages are **open-circuit
   Thevenin levels**; a matched source/load divides the steady-state voltage.
   Set source impedance, separate 10–90% rise/fall times, package R/L/C,
   receiver impedance/capacitance, and VIL/VIH thresholds. Add sources with
   PRBS phase shifts and delays to exercise deterministic aggressors.
3. Attach resistors/capacitors in series with an endpoint or shunt to reference
   at a channel port. All values have defaults. Select a grade, tolerance and
   nominal/min/max corner; replace illustrative parasitics and noise values
   with manufacturer values. Study and passive temperatures must agree.
4. Import an IBIS file, inspect models, typ/min/max tables, waveforms, package
   data, pins and selectors. Bind an explicit model/corner to an endpoint.
   Driver reduction also requires an operating voltage and high/low state.
   Missing corner values, incompatible pins/types, and unsupported electrical
   extensions block reduction instead of being silently dropped.
5. Optionally renormalize reference impedance, reorder ports, add per-port
   electrical delay, or cascade a two-port network on an identical grid.
   Operations execute in order on a copy; endpoint assignments refer to the
   edited order. GUI ports are one-based; JSON ports are zero-based.
6. Run and inspect channel S magnitude/phase, loaded voltage transfer,
   crosstalk, receiver waveform/eye and threshold margins, channel TDR,
   effective passive values, thermal/excess noise, and model limitations.
   The result views also show per-port matched-reference reflection magnitude
   and finite VSWR from the worker's returned samples. Infinite and non-passive
   VSWR samples remain gaps; older saved results without this output show an
   empty plot. TDR reflection is shown separately in the time domain.
   Spatial E/H traces require an AnalysisResult containing actual vector
   samples; this port-network workflow reports field maps as unsupported.
   The network result also reports per-port matched Sii reflection and VSWR;
   ideal unit reflection has infinite VSWR and active reflection above unity
   has no passive VSWR value. These cases carry a status and null VSWR.
   Driving-point impedance terminates every other port in its real reference
   resistance. The result explicitly reports spatial E/H field maps as
   unsupported because port-network samples do not contain field samples.
   Hover charts for trace readings. Source 1 to port 2 is NEXT and source 1
   to port 4 is FEXT for the default coupled ordering. Imported networks need
   the user's explicit port map.
7. Save the complete setup or result as JSON. Completed studies are retained
   in the project's latest SI result and included in the engineering report.
   Export the edited channel as RI/MA/DB Touchstone. Source/receiver/passive
   loading is **not embedded in that channel export**; it remains a separately
   reported loaded-system calculation. A changed setup marks results stale
   until rerun. Unsaved form changes can be retained using **Save setup**.

## Physics and model scope

The loaded solver uses power-wave boundary conditions to solve the complete
multiport linear network with complex terminations. This admits ideal through
networks at DC without a singular intermediate Z matrix. Uniform RLGC
generation uses the multiconductor telegrapher equations, with symmetric
positive-definite L/C matrices. It is an experimental model, not a full-wave
PCB extraction claim. Mixed-mode network inspection and the separate existing
geometry/protocol NRZ/PAM4 workflows remain available in the second tab.

Source capacitance and package capacitance are lumped at the channel-facing
terminal. Receivers place C_comp behind package R/L and endpoint series parts;
receiver waveforms/eyes measure die voltage after that series network. Loaded
transfer curves and port-noise values measure the channel-facing terminals.
No supply/ground bounce or simultaneous-switching power network is inferred.

Time-domain analysis requires explicit DC and uniform frequency spacing;
there is no invented DC, automatic extrapolation, resampling or causality
repair. The sampled spectrum must provide at least eight samples/UI and
represent the requested rate within 1%. Missing bandwidth/grid requirements
block time-domain output while preserving frequency results and export.
PRBS7 uses finite-bandwidth linear convolution. Ramp timing, delays, finite
records and periodic transform tails limit accuracy. Eye measurements use
the first source as the data reference; additional sources are aggressors.
There is no nonlinear switching, CDR or compliance/rare-event BER claim.

IBIS support is an **inventory plus explicit small-signal approximation**,
not a complete nonlinear IBIS or AMI simulator. It uses a selected I/V segment's
incremental resistance and ramp-derived edge time. One slope across an entire
logic swing can be inaccurate. Clamp and waveform tables are retained for
inspection, not switched in the transient solve. Package models are lumped;
external circuits and advanced electrical keywords block this reduction.

## Passive defaults

Capacitor choices include C0G, X7R, X5R, Y5V and Z5U. “Y5” alone is incomplete
and is rejected. Temperature envelopes are classification limits, not curves
to interpolate against temperature. Nominal uses an explicit temperature
factor; min/max apply the complete grade envelope plus manufacturing tolerance.
DC bias factor and aging rate are independent editable assumptions. Defaults
of 1.0 bias factor and zero aging do not assert that a real Class II part has
no bias/aging effects. The UI reports a warning if DC bias is present with
no supplied derating. ESR/ESL and leakage participate in the frequency solve.

Resistor choices include thick film, thin film, metal film and wirewound.
Tolerance, TCR, series inductance, parallel capacitance and current-noise
index are editable. Defaults are examples, not guaranteed technology limits.
Johnson noise is independent of technology at the same R and temperature.
The 1/f excess-noise estimate uses the specified DC voltage and noise index:
the RMS microvolts per volt per frequency decade are `10^(NI/20)`.

Thermal noise is propagated from passive external terminations at the common
study temperature. Resistor excess noise is also propagated to channel-facing
ports over the positive-frequency band, using the supplied bias assumptions.
This calculation excludes internal channel-loss noise and receiver die noise
transfer. Receiver internal noise is listed separately. Noise is **not added
to the plotted deterministic eye waveform**. The finite sampled noise band is
retained in the result; DC excess noise is never treated as finite.

## Worker API and validation

The CLI runs the same service:

```powershell
python -m python.spike_core.cli --output result.json si-workflow study.json --touchstone-output channel.s4p
```

Use `--design design.json` for geometry acquisition and the matching `.s2p` or
`.sNp` output suffix. A blocked requested time-domain or export stage produces
`status: partial` and a nonzero CLI exit status while retaining other results.
Regenerate schemas and the UI default snapshot with
`python scripts/generate_si_workflow_contracts.py`.

Methods: `si_workflow_catalog`, `inspect_si_ibis`, `run_si_workflow`.
`run_si_workflow` accepts `params.request` with contract
`spike/si-workflow-request/v1` and optional `params.design` for board extraction.
Results use `spike/si-workflow-result/v1`, retain the complete request and its
SHA256, and always set `production_qualified: false` and
`compliance_status: not_evaluated`. The desktop routes execution through the
heavy worker and a compatible solver.

Bounds: 2–16 ports, up to 8193 frequency points, 64 attached passives, 32 network
edits, 128–2048 bits, and 1,048,576 waveform samples. Larger arbitrary topology,
nonlinear IBIS/AMI, fixture de-embedding, fitted passive/causal macromodels,
loss-noise correlation, measurement validation and standards qualification
remain further work. This workflow does not claim to complete those features.

Regression checks include analytic loaded dividers and RC transfer, thermal
noise, decoupled/coupled networks, lossless DC, cascades, IBIS pin/corner binding,
schema/default parity and asymmetric known-matrix Touchstone ordering.

## References

### Physical clock correction (2026-09-20)

Loaded NRZ sources now evaluate symbol boundaries at `delay_s + k/bit_rate_hz`
on the FFT grid. They no longer round the unit interval to an integer number
of samples, which previously changed the physical rate or rejected a valid
rate. Finite ramps start at the actual event and carry their state to the exact
end of a UI, not the last sampled point. Fractional source delays are preserved.
Receiver center/eye traces use bounded linear interpolation at the physical
symbol times. No interpolation outside the recorded waveform is accepted.
The normalized geometry-channel NRZ path shares the same symbol-clock helper.
Touchstone export now uses 17 significant digits for binary64 round trips;
the previous 12-digit rounding could destroy uniform spacing in dense grids.

`samples_per_ui` remains the nominal rounded display count;
`actual_samples_per_ui` records the fractional grid ratio and `clock_mode` is
`exact_symbol_boundaries`. `represented_bit_rate_hz` now equals the requested
rate. Source edge sampling, peak-bin cursor alignment and receiver interpolation
remain discretized; this is not a CDR or jitter model. At least eight actual
samples/UI are required, within a small floating-point admission tolerance.

`tests/python/test_si_exact_clock.py` verifies fractional delays, slow ramps,
nonintegral samples/UI, rate invariance across grids, inadequate-band rejection
and comparison to an independently integrated continuous-time RC response.
The latter refines 16/32/64/128 samples/UI, compares at the reported receiver
cursor and requires monotone error reduction and final error below 5mV (1% of
the matched full swing). This tolerance is an analytical regression target,
not a SERDES compliance mask.

### External references

- [IBIS 7.2 specification](https://ibis.org/~ibisorg/ver7.2/ver7_2.pdf): model,
  I/V, ramp, pin and package semantics.
- [Touchstone 2.1 specification](https://www.ibis.org/touchstone_ver2.1/touchstone_ver2_1.pdf):
  two-port special order and row-wise multiport matrices. Older SPIKE builds
  incorrectly transposed 3+ port import/export; nonreciprocal files generated
  by those builds need an explicit migration before relying on port direction.
- [Murata capacitor characteristics](https://article.murata.com/en-us/article/basics-of-capacitors-2):
  grade temperature classifications and capacitance behavior.
- [Murata Class I/Class II comparison](https://www.murata.com/en-global/support/faqs/capacitor/ceramiccapacitor/char/0017):
  why grade is insufficient to specify DC-bias behavior.
- [Vishay resistor technology guide](https://www.vishay.com/docs/49562/49562.pdf):
  resistor technology, parasitics and current noise.
