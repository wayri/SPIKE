<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0073: Separate native device-field and circuit-model execution

Status: first equilibrium kernel implemented; full TCAD requested and pending.

Decision: add an original C++ semiconductor-field subsystem rather than label
PDK compact models as TCAD. `spikes_tcad` exposes a typed Config/Result interface
and `spikes_tcad_console` transports bounded SI inputs and actual native JSON
results. Its first increment is homogeneous 1D equilibrium Poisson-Boltzmann
with prescribed fully ionized doping, checked O(N) tridiagonal Newton steps
and finite residual-decreasing backtracking. No Python numerical state or new
dependency is introduced. Strict floating-point flags remain mandatory.

The owning kernel is independent of circuit MNA and the explicit ngspice PDK
adapter. They may eventually exchange qualified extracted compact models or
mixed-mode boundary conditions, but that coupling is not yet implemented.
Acceptance uses analytical neutrality/mass-action/contact conditions, finite-
volume Gauss balance and continuous manufactured-solution mesh refinement.
Solver residual is not a discretization error estimate or material validation.

Full biased transport, geometry/process TCAD, traps/thermal/quantum models,
native GUI, toolchain packaging and physical qualification remain separate
gates. Admission does not guarantee convergence; failed states remain explicit.
See SPIKES_TCAD_EQUILIBRIUM.md for equations, evidence and completion roadmap.
