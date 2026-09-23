# SPIKES nonlinear language and analysis Wave 6

Wave 6 expands the bounded reference language and semiconductor noise path. It
does not claim complete SPICE3 grammar or production-native nonlinear analysis.

## Behavioral expressions

The safe differentiable expression engine accepts `TABLE(x,x1,y1,...)` with
constant, strictly increasing breakpoints and analytic interpolation gradients.
Values outside the table clamp to the endpoint. A query exactly on an interior
breakpoint fails closed because the derivative is not unique.

SPICE-style `URAMP`, `U`, `SGN`, `FLOOR`, `CEIL`, `INT`, and modulo (`%`) are
also supported. Their gradients are defined away from discontinuities;
boundary evaluations are rejected instead of silently returning a misleading
Newton Jacobian. Dynamic table breakpoints, unsorted tables, arbitrary Python
objects, and unbounded syntax remain prohibited.

## Biased semiconductor noise

Diode `.model` cards accept nonnegative `KF` and positive `AF`. At each
requested positive frequency the reference nonlinear noise analysis propagates
resistor thermal noise, diode shot noise, and
`KF * abs(Ibias)**AF / frequency` through the bias-linearized MNA transfer.
The result records per-source spectra, total output PSD, trapezoidally
integrated variance/noise, and input-referred density when a deck excitation is
available.

Callers may additionally provide bounded complex correlation coefficients,
either constant or frequency indexed. The reference path constructs a
Hermitian source correlation matrix, requires it to be positive semidefinite,
and includes cross-spectral terms in the propagated output PSD.

Wave 6 also includes a frequency-dependent one-source/one-tone third-order
Volterra reference. It builds the linear descriptor matrix at the nonlinear
operating point, evaluates symmetric second/third directional derivatives,
and solves the fundamental, second-harmonic, and third-harmonic systems.

This is a deterministic analytical reference. It does not yet include
device-internal induced-gate noise, BSIM noise equations, cyclostationary
switching noise, arbitrary multi-tone Volterra grids, harmonic balance, or
native sparse frequency sweeps.

## Evidence

- `tests/python/test_spikes_language_analysis_wave6.py`
- `tests/python/test_spikes_language_analysis_wave4.py`
- `tests/python/test_spikes_language_analysis_wave5.py`
- `python/spikes/behavioral.py`
- `python/spikes/nonlinear_analyses.py`
- `python/spikes/nonlinear_deck.py`
