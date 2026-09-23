# SPIKES C ABI

`src/spikes/c_api.h` is the language-neutral ownership boundary for the native
SPIKES circuit kernel. Callers receive opaque circuit and result handles and
must release them with the matching destroy functions. No C++ standard-library
type crosses this boundary.

## Versioning decision

`SPIKES_ABI_VERSION` remains `1` after the transient API was introduced. The
change only adds exported functions and a new opaque result type; no existing
symbol, enum value, function signature, ownership rule, or public structure was
changed. Existing ABI-v1 binaries can continue resolving and calling the old
surface unchanged.

Transient options have their own `SPIKES_TRANSIENT_API_VERSION == 1` contract.
Callers should initialize `spikes_transient_options` with
`spikes_transient_options_init`, retain the returned `struct_version` and
`struct_size`, and then override desired fields. The solver rejects unknown
versions, undersized structures, and invalid values. A future breaking change
to the existing ABI will increment `SPIKES_ABI_VERSION`; additive transient
option fields can instead use the structure size/version negotiation.

DC linear-solver options use the independent
`SPIKES_LINEAR_SOLVER_API_VERSION == 1` structure. The additive entry point can
select automatic dispatch, pivoted dense LU, Jacobi-preconditioned conjugate
gradient, row-equilibrated restarted dense GMRES, COLAMD-ordered sparse LU,
rank-revealing sparse QR, or row-equilibrated ILUT-preconditioned sparse GMRES. Explicit CG requests reject
nonsymmetric or non-positive-definite MNA systems; both GMRES paths accept
general MNA and verify their final residual against the original unscaled
equations. Automatic dispatch retains dense LU for small systems, sparse LU for
larger systems, and attempts ILU-GMRES before sparse LU at the largest current
threshold. The Eigen sparse backends currently report one controlled worker;
multicore sparse factorization is not implied.

`spikes_result_sparse_solver_diagnostics` additively reports structural
nonzeros, symbolic analyses, and numeric factorizations without changing any
ABI-v1 structure. Nonlinear DC reserves its complete Jacobian pattern before
Newton iteration, permitting sparse LU to reuse symbolic ordering while values
are refactorized.

The transient result is immutable and independently owned. Point queries are
index based and return `SPIKES_NOT_FOUND` for invalid indices or names. The
current ABI-v1 status enum maps nonlinear nonconvergence to
`SPIKES_SOLVE_NUMERICAL_FAILURE`; the result message and diagnostics retain the
more specific cause without changing the meaning of old enum values.

## Switching-source surface

ABI v1 now has additive constructors for periodic PULSE and arbitrary PWL
voltage/current sources. PWL points cross the boundary as a caller-owned
`spikes_pwl_point` array which is copied before the call returns. PULSE edges
and PWL knots are hard transient breakpoints: the C++ solver reduces its step
to land on them instead of stepping across them. The configured `max_steps`
remains a hard bound after those additional steps are included.

The additive `spikes_circuit_add_voltage_controlled_switch` constructor creates
a bidirectional, finite-Ron/Roff switch with a smooth control transition and an
analytic control Jacobian. This is the initial switching-converter primitive;
it is not a MOSFET compact model. All new constructors are also bound by the
explicit `python.spikes.native_abi` bridge. Older ABI-v1 libraries are detected
by symbol availability and fail closed if a caller requests an absent feature.

The additive `spikes_circuit_add_dynamic_diode` constructor creates a
two-terminal charge-control device. It stamps one implicit diffusion-current
state plus junction capacitance, supports backward Euler and variable-step
BDF2, and exposes reverse-recovery current through the ordinary element-result
surface. Hybrid trapezoidal requests fail closed for circuits containing this
device until a charge-consistent trapezoidal companion is qualified. The
Python bridge feature-detects the symbol, preserving compatibility with older
ABI-v1 libraries.

Two further additive constructors expose bounded coupled DAEs without changing
an existing structure: `spikes_circuit_add_electrothermal_resistor` stamps
temperature-dependent resistance, Joule power, Rth, and Cth on a distinct
temperature-rise node; `spikes_circuit_add_saturating_inductor` stamps a smooth
flux-linkage law parameterized by unsaturated/saturated inductance and knee
current. Both support backward Euler and variable-step BDF2, participate in the
embedded nonlinear LTE solve, and currently reject hybrid trapezoidal mode.

## Additive DC compact-device surface

ABI v1 also has additive constructors for a three-terminal Ebers-Moll BJT and
a four-terminal Level-1 Shichman-Hodges MOSFET. Their nonlinear residuals and
Jacobians are stamped into the owned native DC MNA system and participate in
its sparse structural pattern. The BJT and Level-1 MOSFET models are
intentionally bounded: this is not BSIM, and neither device currently supplies transient terminal charge,
noise, self-heating, breakdown, or vendor-card compatibility. Native transient
analysis rejects these DC-only transistor elements rather than silently
omitting their dynamic behavior.

The additive five-terminal WBG constructor provides a separate bounded GaN
HEMT/SiC MOSFET constitutive model with bidirectional conduction, avalanche,
temperature-dependent current, conservative linear terminal charge, and an
explicit `Rth-Cth` temperature-rise state. Backward Euler and BDF2 integrate
charge and temperature; hybrid trapezoidal rejects the model. This is not a
vendor-qualified ASM-HEMT, BSIM-CMG/BSIM-BULK, HiSIM-HV, or foundry model.

`spikes_transient_result_breakpoint_steps` is an additive diagnostic query for
the number of accepted steps shortened specifically to land on a source edge
or knot. The Python bridge detects the symbol and includes
`source_breakpoint_steps` when it is available.

`spikes_solve_transient_with_method` additively selects backward Euler,
hybrid trapezoidal, or variable-step BDF2 without changing the versioned options
structure or the legacy `spikes_solve_transient` behavior. Hybrid mode uses BE
at startup/source breakpoints and trapezoidal companions between events; BDF2
uses unequal-step coefficients and restarts through BE after discontinuities.
`spikes_transient_result_integration_diagnostics` reports the accepted step
count for each method. `spikes_transient_result_factorization_diagnostics`
reports dense LU constructions, reuse solves, and bounded cache occupancy.

`spikes_solve_transient_adaptive` is an additive, opt-in embedded-order
controller. Smooth BDF2 and trapezoidal steps are paired with a BE companion
solve at the same endpoint and history; their scaled defect controls rejection
and step selection. Minimum-step and rejection bounds remain explicit.
Adaptive BE-only and nonlinear requests fail closed until a corresponding
embedded nonlinear pair exists. `spikes_transient_result_lte_diagnostics` and
`spikes_transient_result_sparse_lte_diagnostics` report rejection, defect,
accepted-step, embedded-solve, sparse-assembly, symbolic-analysis, numeric
factorization, and numeric-only refactorization counts.

Linear and nonlinear transient systems at the native size threshold are
assembled directly as sparse triplets, including analytic nonlinear Jacobian
contributions. SparseLU performs COLAMD symbolic analysis once per pattern
and repeats only numeric factorization when companion values change. Exact
unchanged matrices reuse the numeric factorization. Dense nonlinear assembly
remains available as the small-system reference path.

## Persistent transient session surface

The additive opaque `spikes_transient_session` API copies a circuit snapshot
once, permits bounded updates to constant independent sources, advances one
accepted step at a time, and exposes the current V/I/P values, position,
status, and cumulative diagnostics. Opaque checkpoints preserve native dynamic
state and source values; the C boundary rejects restoration into a different
session. The explicit Python bridge owns the same handles and provides
context-managed `NativeTransientSession` and `NativeTransientCheckpoint`
objects.

Session v1 supports backward Euler, hybrid trapezoidal, and BDF2 integration with
constant, PULSE, and PWL independent sources. PULSE/PWL values and exact
internal breakpoints are translated from the persistent global clock for every
requested interval; checkpoint restore also restores that clock and the
capacitor-current/inductor-voltage companion history. Hybrid sessions use BE
at startup and real waveform events, then trapezoidal companions between
events. BDF2 sessions preserve and checkpoint two accepted solution/history
levels and restart through BE at real waveform events. Only constant sources are mutable. The
circuit/state handle and a bounded 64 MiB/16-entry LU workspace are persistent.
Each dense matrix is still assembled per step, then matched coefficient-wise
at strict machine-epsilon-relative tolerance before any reuse. The additive
session factorization diagnostic reports reuse and cache occupancy. This is
not a preallocated hard-real-time kernel.

`spikes_transient_session_element_voltage` is an additive ABI-v1 query for the
current signed terminal voltage of a named element. Together with the existing
node-voltage, element-current, and element-power queries, it lets compiled
dashboards attach complete V/I/P probes to a persistent simulation without
constructing a new transient-result object. Older ABI-v1 libraries remain
loadable; the Python bridge detects this symbol separately and fails closed if
an element-voltage query is requested from an older binary.

The native release also installs `spikes_core` and `spikes_dashboard` static
libraries for C++ callers and `spikes_console` as an application. These C++
surfaces do not have the ABI stability guarantee of `spikes_c_api`; external
binary integrations that need a stable language-neutral boundary should use
the C ABI.
