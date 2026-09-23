# SPIKES native switching kernel

The owned C++ SPIKES kernel now supports constant, periodic PULSE, and PWL
independent voltage/current sources in DC initialization and transient solves.
Transient integration supports backward Euler and an event-aware hybrid
trapezoidal method. The hybrid method uses backward Euler for startup and every
step that lands on a PULSE phase boundary or PWL knot, then uses the
second-order trapezoidal companion models between events. `time_step_s` is a
maximum: every source breakpoint inside a proposed step becomes an exact solve
point. This prevents PWM edges from moving with the requested output grid. The
solver counts inserted steps and fails closed at `max_steps`.

The first native converter switch is a four-terminal voltage-controlled,
bidirectional conductance. Its model parameters are finite on resistance,
finite off resistance, threshold voltage, and positive transition voltage.
A hyperbolic-tangent blend gives continuous conductance and an analytic
control derivative. The Jacobian includes both output conductance and control
transconductance terms. Reverse terminal voltage therefore produces reverse
current without changing the model, enabling synchronous and regenerative
test circuits.

These capabilities are available through:

- the C++ `spikes::Circuit` API;
- additive C ABI functions in `src/spikes/c_api.h`;
- the explicit local-library Python bridge in `python/spikes/native_abi.py`.

Dense LU factorizations are cached and reused when the companion matrix is
unchanged. Linear matrices are keyed by exact step size and integration method;
nonlinear Jacobians are reused only on exact matrix matches. Both caches are
bounded (16 entries, with a 64 MiB nonlinear-Jacobian memory ceiling), and the
result reports factorization, reuse, cache-entry, backward-Euler-step, and
trapezoidal-step counts. The committed five-period PWM fixture performs 21
factorizations and 44 reuse solves over 45 accepted steps on the current dense
kernel. These are work counters, not a runtime superiority benchmark.

The current kernel remains a correctness-first dense MNA implementation. It
does not yet contain sparse symbolic ordering/numeric refactorization,
local-truncation-error step control, Gear/BDF2 selection, event-state
hysteresis, semiconductor charge storage, or production converter compact
models. Those remain required before switching-performance claims are eligible.

Regression fixtures cover PULSE edge alignment, PWL interpolation and knot
alignment, inserted-step work bounds, hybrid-method accuracy, event damping,
factorization reuse, on/off switching, reverse conduction, invalid model
rejection, C ABI transport, and Python closed-loop access.
