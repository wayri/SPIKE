# Public application corpus provenance

Review date: 2026-08-31

These are first-party synthetic circuits written for SPIKES qualification.
They contain only ideal independent sources and standard lumped R/L/C parts;
there are no vendor models, copied decks, measured datasets, or third-party
parameter sets. `LICENSE.txt` applies CC0-1.0 to the `.cir` files.

The fixtures intentionally isolate three application-domain behaviors:

- `converter_pwm_lc.cir`: ideal PWM switch-node excitation and output filter;
- `rf_series_resonator.cir`: series-resonator AC sweep around resonance;
- `motor_fixed_speed_armature.cir`: R-L armature with fixed back EMF.

These are transparent equal-model correctness fixtures. They do not by
themselves qualify semiconductor switching loss, distributed RF/EM behavior,
or a coupled motor electromagnetic/mechanical field model.
