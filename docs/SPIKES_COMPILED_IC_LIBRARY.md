<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKES compiled IC library

`compiled_ic_library.py` supplies reusable, data-only descriptors for the existing
Studio sampled C/C++ controller bridge. The initial catalog contains a generic
edge-aligned PWM block and a generic PI block. These are controller examples,
not manufacturer IC models.

## Workflow

In Studio's Controller workspace, choose **Block library…**, select a block,
edit its labeled parameter fields and choose **Load into editor**. Imported and
exported `.spkctl` files are data-only library descriptors. Loading closes any
previous compiled instance, disables attachment and clears trust consent. It
does not alter the schematic or save setup until **Apply / save setup** is used.
Review **Pin properties…**, explicitly approve the code, then compile and run.
The UI retains normal project undo when applying the resulting setup.

Use `catalog()` to inspect the descriptor metadata and `configuration(id,
parameters, pins)` to produce a validated `spikes/generic-controller/v1`
configuration. Pin overrides bind AI/DI pins to node/reference names and AO/DO
pins to an existing independent DC voltage source. The returned configuration
can be passed to `Controller` only with the existing explicit `trusted=True`
consent. Merely calling `catalog()`, `load()`, or `save()` never invokes a
compiler and never executes descriptor source.

The package contract is `spikes/compiled-ic-library/v1`. `save()` writes the
bounded JSON form and `load()` checks its contract, duplicate keys, identifiers,
parameters, pins, state, and controller compatibility. Imported source remains
untrusted data. Loading it does not approve later execution.

## Sampled execution contract

Each descriptor declares:

- input and output pin modes, default circuit bindings, and voltage envelopes;
- bounded numeric parameters with units and defaults;
- ordered explicit state entries corresponding to `state[0]`, `state[1]`, and
  so on in the existing controller bridge;
- a controller sample period and C/C++ source template; and
- limitations that remain attached to the descriptor.

The PWM carrier phase is an explicit integer-valued tick-count state. Its output
is evaluated from the count at the current tick, then the count advances by one
for the next tick. Its switching period must contain an integer number of
controller ticks and at least two ticks. The admitted parameter bounds limit a
period to at most `1e12` ticks, below binary64's exact-integer limit, so carrier
updates and wrap do not accumulate floating-point phase drift. Every PWM edge is
quantized to the controller sample grid. The PI
integral contribution is explicit state and updates once per controller tick;
conditional anti-windup prevents further integration into an active output
limit for an error of the same sign.

The Studio plant coupling applies a controller only at accepted native session
points and requires its sample period to be an integer multiple of the circuit
output timestep. Reset sets all explicit state to zero. C static/global storage
does not persist because each tick runs in a fresh subprocess.

## Scope and limitations

These blocks establish only deterministic execution of the documented sampled
equations through the existing digest-approved process boundary. They do not
model continuous-time IC physics, internal transistor circuits, analog PWM ramp
behavior, propagation delay, dead time, jitter, ADC/DAC quantization, noise,
thermal behavior, firmware timing, or hardware protection. They provide no
closed-loop stability claim, HIL timing claim, safety claim, or vendor
qualification. Native source executes with the user's permissions and is not a
hostile-code sandbox; every compile still requires explicit trust.

## Verification

`test_compiled_ic_library.py` checks descriptor validation, parameter and pin
binding, data-only round trips, malformed imports, and actual C compiler/process
execution. The PWM regression checks its four-tick carrier sequence and retained
phase; the PI regression checks two accepted integral updates. Those tests cover
the sampled examples and bridge lifecycle only, not any physical IC.
