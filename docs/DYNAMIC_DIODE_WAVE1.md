# Dynamic diode Wave 1

`python/spikes/dynamic_devices.py` is an executable, bounded reference for the
first charge-aware compact-device slice. It provides:

- temperature-scaled Shockley conduction and an analytic conductance;
- junction depletion charge/capacitance with a continuous high-forward-bias
  continuation;
- mobile transport charge integrated by implicit Euler;
- reverse-recovery current after stored forward charge is reverse-biased;
- an analytic transient terminal-current Jacobian; and
- fail-closed voltage, temperature, current and timestep validity limits.

The terminal current used by `DynamicDiodeModel.advance` is

`i = i_conduction + d(q_depletion)/dt + d(q_transport)/dt`.

Transport charge obeys `dq_transport/dt = max(i_conduction, 0) -
q_transport/transit_time`. The implementation returns the updated immutable
state so a caller owns all history and can checkpoint it without hidden state.

## Current integration status

This is a constitutive-model reference, **not** a production/vendor-qualified
device and **not yet stamped into the native sparse MNA/transient solver**. It
does not currently include avalanche breakdown, series-resistance implicit
solving, high-level injection, recombination current, self-heating, or a
vendor-parameter compatibility mapping. Those features require separate model
qualification and native-solver integration before the model can close the
production-device parity item.

Run its analytic and regression tests with:

```text
python -m unittest tests.python.test_spikes_dynamic_devices -v
```
