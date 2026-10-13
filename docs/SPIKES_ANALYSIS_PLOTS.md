<!-- SPDX-License-Identifier: Apache-2.0 -->
# Recorded-signal analysis plots

Open **Analysis plots...** on the waveform toolbar or waveform context menu.
The floating window captures the selected retained run; changing the main run
does not change its data. Signal expressions reuse dimensional SignalMath, e.g.
`v(out)`, `v(p,n)`, `v(out)*i(load)`, or `v(actual)-v(reference)`.
Blank start/stop fields use the complete retained interval. Calculations run in
one bounded background worker, not the GUI event handler or live solver.

| View | Meaning and limits |
| --- | --- |
| XY / phase portrait | Separate X/Y expressions; ordered display sampling capped at 4096 points, which can hide small loops |
| FFT peak amplitude | One-sided, linear amplitude; caller-selected Hann/rectangular window, coherent-gain correction; DC/Nyquist not doubled |
| Power spectral density | One-sided periodogram in signal-unit squared/Hz; window-energy normalization; not Welch averaging or a device noise solver |
| Eye diagram | Caller-supplied symbol period; two-symbol windows with piecewise-linear interpolation; at most 256 windows, 256 displayed points each |
| Histogram | 2..256 bins; counts from original samples, sample-weighted rather than duration-weighted |
| Cumulative integral | Trapezoidal signed integral on original timestamps; power integrates to joules when current/voltage sign conventions are appropriate |

Each calculation requires 3..262144 selected samples. FFT/PSD additionally
requires a uniform time grid within 1 ppm; there is no silent resampling or
anti-aliasing assumption. Eye diagrams require at least eight retained samples
per symbol and two complete periods. Unknown expressions, complex-valued
transient coordinates, out-of-range intervals and nonfinite results are rejected.
Use explicit real/imag/abs expressions where appropriate. DC is not removed.

Mean/RMS are time-weighted trapezoidal reductions, using scaled amplitudes to
avoid unnecessarily overflowing the square. Display decimation does not change
these readings. Spectral peak and integrated PSD use all selected spectral bins,
not the decimated curve. Integrated PSD and time-weighted RMS are different
estimators, especially for windows/nonperiodic records. Neither establishes
measurement bandwidth outside the retained sample grid.

Mouse wheel zooms X; Shift-wheel or the Y-axis gutter zooms Y. The Matplotlib
toolbar provides pan, box zoom, history and image export; right-click provides
fit, grid toggle and export. Window controls disable irrelevant inputs. Failed
calculations leave the previous plot intact and show the failure instead of
substituting a synthetic curve.

Existing frequency workspace views remain separate: Bode, real/imaginary,
Nyquist, polar, Nichols, group delay, Smith impedance/admittance, return loss,
VSWR and pole-zero. Their existing backend/model restrictions still apply.
Neither a plot type nor an example establishes nonlinear RF/harmonic-balance,
IBIS/AMI, jitter/BER, precision-amplifier noise, EMI compliance, insulation/arc,
electrothermal safety or manufacturer-model qualification.

Implementation: `analysis_plots.py` owns headless reductions/rendering;
`analysis_plot_window.py` owns the captured-run worker and floating window.
Tests include coherent sine amplitude, DC/Nyquist scaling, Parseval/PSD energy,
Hann gain, constant/irregular-grid integration, histogram totals, invalid
sampling and a real owned-C++ RC result through native controls.
`ui_analysis_plot_evidence.py` captures only actual C++ result plots.

Method references: [NumPy DFT conventions](https://numpy.org/doc/stable/reference/routines.fft.html)
and [SciPy spectral-analysis definitions](https://docs.scipy.org/doc/scipy/tutorial/signal.html#spectral-analysis),
accessed 2026-10-12. The normalization and tests are independently authored;
no external source code or examples were copied. For DFT Y of samples y times
window w, amplitude is c*abs(Y)/sum(w); PSD is c*dt*abs(Y)^2/sum(w^2),
with c=2 except DC and even-length Nyquist, where c=1. Analytical sinusoidal
and constant-signal oracles establish only these stated processing conventions.
Knowledgeable numerical review is still required before release.
