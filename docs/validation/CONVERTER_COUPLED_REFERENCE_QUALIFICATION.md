# Converter coupled-reference qualification

This qualification corpus covers four bounded converter behaviors:

- freewheel-diode stored-charge commutation and reverse recovery;
- temperature-dependent switch conduction loss coupled to a thermal RC;
- current-dependent differential inductance entering and leaving saturation;
- ordered overcurrent warning, trip, delayed gate shutdown, and current decay.

Run it with:

```powershell
python scripts/run_spikes_converter_qualification.py --output artifacts/spikes-converter-coupled-reference-qualification.json
```

Every case records its model, numerical metrics, ordered events, executable
gates, and explicit limitations. The report fails closed if execution or any
gate fails. JSON output rejects non-finite values.

## Scope boundary

These are deterministic, coupled **reference** models. They do not stamp or
advance the native MNA/DAE kernel. In particular, this evidence does not
qualify native reverse-recovery, electrothermal, or magnetic device models; a
vendor compact model; spatial thermal or field physics; hard real-time
execution; HIL; or a performance/accuracy claim against another simulator.

The report therefore always sets `native_mna_integration_qualified`,
`production_compact_models_qualified`, `hard_realtime_qualified`,
`hil_claim_eligible`, and `competitive_claim_eligible` to `false`.

## Gate basis

The reverse-recovery case checks the model's exact discrete charge balance and
its analytic implicit-Euler decay time. The electrothermal case correlates to
the closed-form fixed point of a stable positive-feedback thermal loop. The
magnetic case compares the nonlinear PWM ramp with an analytic linear-inductor
reference and requires ordered saturation entry and exit. The protection case
correlates warning and trip crossings to the closed-form RL response and
requires warning, trip, shutdown, and extinction in safety order.
