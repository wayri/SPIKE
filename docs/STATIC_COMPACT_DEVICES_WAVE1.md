# Static compact devices Wave 1

`python/spikes/static_compact_devices.py` adds bounded executable DC reference
models with terminal currents defined positive into each device. Every result
enforces KCL, and every Jacobian has zero row/column sums (voltage-reference
invariance and terminal-current conservation).

Included models:

- `EbersMollBJT`: NPN forward/reverse Ebers–Moll transport, temperature-scaled
  junction saturation currents, and a closed-form analytic C/B/E Jacobian.
- `Level1MOSFET`: bidirectional n-channel Shichman–Hodges cutoff, linear and
  saturation regions, channel-length modulation, body effect, threshold drift,
  mobility scaling, and a bounded numerically qualified D/G/S/B Jacobian.
- `ShichmanHodgesJFET`: bidirectional n-channel cutoff, linear and saturation
  regions, mobility scaling, channel-length modulation, and a bounded
  numerically qualified D/G/S Jacobian.

The validity contract rejects non-finite/out-of-range terminal voltages,
temperatures, currents and parameters. It does not silently clamp values.

## Scope boundary

These are constitutive references and are **not stamped into the native MNA
solver**. The MOSFET is Level 1, not BSIM; none of the models is vendor-qualified.
They omit capacitance/charge dynamics (covered only by the separate diode Wave-1
reference), breakdown, leakage refinements, noise, self-heating, geometrical
binning and foundry parameter mappings. Production parity remains open until
native integration and qualification against public/vendor data are complete.

Run the qualification tests with:

```text
python -m unittest tests.python.test_spikes_static_compact_devices -v
```
