# Studio board co-simulation

The SPIKE worker exposes `prepare_studio_board_context`,
`validate_studio_board_cosimulation` and `run_studio_board_cosimulation`.
Preparation takes `{design}`; validation/execution take `{design, request}`.
The neutral SpiDeR payload is normalized and hashed on the server. Its board
revision and canonical resistor component aliases must match every binding.
A changed board requires preparation again. Selecting a component does not
establish a thermal or semiconductor model.

## Supplied model

Request contract: `spike/studio-board-cosimulation-request/v1`.
Top-level fields are `netlist`, `board_revision`, `mode` (`steady_state` or
`transient`), `bindings`, `thermal`, and `controls`, in addition to `contract`.
Every resistor has one binding with `element_id`, `component_id`,
`thermal_node_id`, `reference_temperature_k`, and
`temperature_coefficient_per_k`. Board element names use the same canonical
alias helper as circuit-workspace composition. Actual pad connectivity remains
an explicit circuit-workspace input, not an inferred board electrical extraction.

Thermal fields are `ambient_temperature_k`, `nodes` and `links`. Nodes require
`id`, `capacitance_j_per_k`, `initial_temperature_k`, `minimum_temperature_k`
and `maximum_temperature_k`. Links require `id`, `from_id`, `to_id` and
`resistance_k_per_w`. The reserved endpoint `ambient` represents the supplied
boundary temperature. Every node needs an explicit path to ambient. No package
resistance, capacity, cooling coefficient or material constant is guessed.

Controls require `window_s`, `electrical_step_s`, `stop_time_s`,
`maximum_iterations`, `temperature_tolerance_k`, `power_tolerance_w`,
`balance_tolerance_w`, `relaxation` and `time_limit_s`. The contract admits at
most 128 circuit elements, 32 thermal nodes, 2000 windows, two million replay
steps and a 120-second cooperative wall budget. Serialized requests/results
are bounded to 8 MiB. The host can terminate a worker blocked inside a native call.

## Coupling and numerical meaning

Native SPIKES MNA solves supplied resistor, ideal capacitor/inductor and constant
ideal-source circuits, with constant, continuous PWL or finite-rise/fall PULSE
supplies. Steady mode iterates operating points and a steady
lumped thermal solve. Transient mode preserves a native electrical session and
uses backward Euler in both subsystems. Ordinary `.tran` initializes from OP;
explicit UIC preserves the native supplied-initial-condition semantics. Initial
OP storage states are frozen into explicit C/L initial conditions before creating
the replay session, so Picard resistor changes cannot recalculate the start state.
For each communication window, native checkpoints roll back electrical state
before each fixed-point trial. Endpoint resistor powers, integrated over bounded
electrical substeps, provide average thermal power. Substeps stop at every
PWL/PULSE corner; each returned native step must represent exactly one accepted
internal step. Hidden subdivision fails closed instead of silently losing heat. Accepted endpoint temperature
feeds the next trial through `R(T) = Rref * (1 + alpha * (T - Tref))`.

Unrelaxed temperature changes, changes in window heat and independently computed
thermal nodal balances must all meet caller tolerances. Electrical transient
steps additionally check source work equals resistor heat plus stored-energy
change plus backward-Euler numerical dissipation. For a capacitor this last term
is `C * (delta V)^2 / 2`; for an inductor it is `L * (delta I)^2 / 2`.
This separates integration damping from physical device heating.

Optional binding `geometry` requires `length_m`, `width_m`, `thickness_m`,
`resistivity_ohm_m` and `expansion_per_k`. Its reference `rho*L/(width*thickness)`
must agree with netlist resistance within relative 1e-6. Uniform isotropic
expansion multiplies all three dimensions by `s=1+expansion*(T-Tref)`, giving
`R(T)=Rref*(1+alpha*(T-Tref))/s`. Returned dimensions are explicit reduced
parameter re-extraction, not a deformed CAD mesh or a mechanical solution.
Feedback stays inside positive supplied temperature/dimension ranges and the
native transient resistance setter range of 1e-6 through 1e15 ohm.

## Accepted results and recovery

Each accepted frame records time, temperatures, applied feedback temperatures,
thermal-node powers, electrical voltages/currents/powers/resistances, explicit
geometry parameters, residuals and iteration count. Transient frames include
source/heat energy, starting/ending stored energies, integration damping and
maximum electrical step balance error. The result retains the normalized board
revision, input and native-library hashes, mappings and complete loss ledger.
A worker stderr progress frame publishes `{accepted_frame: frame}` only after
acceptance. Frames are approximate reduced-model outputs, not qualified fields.

Cancellation, timeout, nonconvergence and invalid input have distinct statuses;
prior accepted frames remain available. Failed trial state is rolled back.
Native checkpoints are internal and released after each window. Returned history
hashes establish provenance; they are not serialized native restart checkpoints.
Rerun from the request after editing controls or supplying missing model data.

## Evidence and limitations

`tests/python/test_studio_board_coupling.py` contains original synthetic oracles:
constant-current thermal RC backward-Euler identity and continuous-time step
refinement, current-fed R(T) steady equilibrium, actual electrical RC history
across rollback, OP/UIC distinction, and the closed-form geometry-feedback
quadratic. Admission and failure cases cover mismatched board identity/alias,
missing mappings, reference geometry mismatch, unsupported sources/sweeps,
native setter bounds, cancellation and unrelaxed nonconvergence. A narrow pulse
wholly inside the old sample interval retains heat and converges to the analytical
ramp-energy integral after electrical refinement. Nonuniform PWL/replay, transient
R(T), first-window divider storage and timeout checks are also executable.

Independent derivations use Kirchhoff power balance, lumped `C*dT/dt+G*(T-Ta)=P`
and resistor geometry laws; no external implementation or dataset was copied.
These analytical fixtures establish bounded software behavior, not hardware
correlation. Conditioning worsens with high resistance ratios or strong thermal
positive feedback; failure is retained rather than relabeled stable. Electrical
and communication step refinement is required for a new engineering case.

Semiconductors, arbitrary behavioral devices, discontinuous PULSE edges, source
waveforms other than continuous PWL/finite-rise-fall PULSE, parameter sweeps, automatic PCB parasitic extraction, spatial thermal
fields, airflow, FEM deformation and hard real-time/HIL are unsupported here.
Existing native PWM/retained-volume studies have separate contracts and evidence.
Numerical code requires knowledgeable human review before release.

Workspace composition emits an ngspice ASCII output hint. Admission reuses the
owned-workspace normalizer to remove only exact `.options filetype=ascii`; all
other option directives remain rejected. The supplied request hash includes
the original composed text.
