<!-- SPDX-License-Identifier: Apache-2.0 -->
# Multiphysics frontier research candidates

Snapshot checked on 18 October 2026. This is a selective primary-source shortlist,
not an exhaustive latest-paper survey. All entries are **candidate/design
guidance**; none is an implementation or validation claim for SPIKE. Newer dates
do not replace established mathematical foundations or make a method universally
more accurate. See [platform strategy](MULTIPHYSICS_PLATFORM_STRATEGY.md),
[evidence policy](NUMERICAL_METHOD_EVIDENCE.md) and
[existing reference lineage](SOLVER_REFERENCES.md).

Source identity, abstracts and official/publisher records were checked. A separate
research scan inspected selected method/limitation material. This is not a full
derivation audit of every paper. Before implementing, record the exact equations,
assumptions/sections reviewed and independent derivation. No external source code,
figures, meshes or fixtures are adopted by this survey.

## Candidate methods and promotion gates

| Candidate and primary reference | What the source establishes | SPIKE experiment and acceptance — proposed engineering judgment |
| --- | --- | --- |
| Differentiable CFD: Deniz A. Bezgin, Aaron B. Buhendwa, Nikolaus A. Adams, *JAX-Fluids 2.0: Towards HPC for Differentiable CFD of Compressible Two-phase Flows*, submitted 7 February 2024, [arXiv:2402.05193](https://arxiv.org/abs/2402.05193). | Demonstrates differentiable compressible single/two-phase flow and parallel accelerator execution for its selected models/tests. This does not establish gradients through arbitrary shocks, remeshing, contact or turbulence objectives. | Start with a validated smooth forward problem. Verify directional derivatives/Taylor remainders against independent perturbations; sweep solver tolerances, mesh/time steps and objective definitions. Explicitly handle nonsmooth regimes. This is a method reference, not a decision to introduce JAX into SPIKE. |
| Differentiable structures: Gaoyuan Wu, *JAX-SSO: Differentiable Finite Element Analysis Solver for Structural Optimization and Seamless Integration with Neural Networks*, submitted 29 July 2024, [arXiv:2407.20026](https://arxiv.org/abs/2407.20026). | Uses adjoints/automatic differentiation for structural optimization examples including shells. Forward accuracy, gradient accuracy and design performance remain distinct questions. | Verify established elasticity and objective gradients before topology/shape optimization. Check perturbation and mesh sensitivity, parameter bounds and constraint feasibility. Do not infer generic nonlinear/contact adjoints from these examples. |
| GPU matrix-free/high-order preconditioning: Will Pazner, Tzanio Kolev, Jean-Sylvain Camier, *End-to-end GPU acceleration of low-order-refined preconditioning for high-order finite element discretizations*, 21 October 2022 preprint, [arXiv:2210.12253](https://arxiv.org/abs/2210.12253), [related publication DOI](https://doi.org/10.1177/10943420231175462). | Develops low-order-refined preconditioning for high-order spaces, including curl/divergence-conforming problems and adaptive-mesh/magnetic-diffusion examples. An older foundation remains relevant to current acceleration research. | Compare assembled/matrix-free operators and converged observables; sweep size/order/material contrast and hardware. Measure setup, communication, preconditioner, solve, memory and I/O at equal error. A GPU kernel speedup is not an end-to-end simulation speedup. |
| Conservative multirate coupling: Bochev, Owen, Kuberry and Connors, *A conservative discontinuous-Galerkin-in-time (DGiT) multirate time integration framework for interface-coupled problems with applications to solid–solid interaction and air–sea models*, 1 June 2024, CMAME 426:116975, [Sandia record](https://www.sandia.gov/research/publications/details/a-conservative-discontinuous-galerkin-in-time-dgit-multirate-time-integrati-2024-06-01/), [DOI](https://doi.org/10.1016/j.cma.2024.116975). | Extends a multirate framework to specific coupled elastic-solid and rotating thermal shallow-water systems. Different subsystem time scales introduce stability/conservation questions, not merely scheduling. | Begin with analytically checked coupled oscillators/heat transfer, then a targeted application and converged monolithic reference. Sweep coupling strength/timestep ratio; verify interface flux cancellation, work/energy, temporal order and rollback. Electrical/thermal/FSI adoption needs its own derivation. |
| Learned operators with uncertainty/conservation: S Chandra Mouli et al., *Using Uncertainty Quantification to Characterize and Improve Out-of-Domain Learning for PDEs*, ICML/PMLR 235, 21–27 July 2024, [proceedings](https://proceedings.mlr.press/v235/mouli24a.html). | Shows failures of several uncertainty methods under moderate distribution shift, and empirical improvements using DiverseNO/Operator-ProbConserv on selected PDEs. Selected conservation constraints and uncertainty/error correlation do not give a universal error certificate. | Hold out complete geometry/material/boundary/operating families. Test field and engineering-observable error, conservation, uncertainty calibration, long-horizon drift and failure detection separately. Require abstention and fallback to a validated solver; include training/reference-data cost in throughput claims. |
| Unfitted conservative discretizations: Thomas Frachon, Erik Nilsson, Sara Zahedi, *Divergence-free cut finite element methods for Stokes flow*, BIT Numerical Mathematics 64:39, 5 October 2024, [publisher/DOI](https://doi.org/10.1007/s10543-024-01040-x). | Studies divergence-free unfitted Stokes formulations with specific stability and boundary-enforcement properties. The studied two-dimensional setting is not qualification of arbitrary 3D turbulent moving geometry; pressure/boundary error and conditioning require attention. | Sweep boundary translations/tiny cut fractions; verify manufactured convergence, divergence, boundary leakage, pressure robustness, flux/force and conditioning. Test geometric quadrature independently. New moving/3D/Navier–Stokes extensions require separate evidence. |
| Unified fracture/contact: Jaemin Kim, Gukheon Kim, Sungmin Yoon, Dong-Hwa Lee, *A unified variational framework for phase-field fracture and third-medium contact in finite deformation hyperelasticity*, arXiv submission record 27 February 2026, [arXiv:2603.15635](https://arxiv.org/abs/2603.15635). **Preprint/research only.** | Proposes a common regularized energy treatment and illustrates bending/Brazilian-disk cases. This is not a general qualified fracture/contact/material library. | Establish separate contact/fracture references first, then test coupled force–displacement, energy and irreversibility. Sweep fracture length scale versus mesh, contact regularization, load increments and conditioning. Friction, inertia/impact and thermal-fracture need their own supported formulations and measurements. |

Priority recommendation: invest first in scalable preconditioning, conservative
coupling and verified sensitivities, which benefit several existing domains.
Evaluate learned models, unfitted geometry and new fracture formulations as
bounded opt-in experiments. A promising abstract warrants evaluation, not feature
promotion. GPU acceleration, automatic differentiation, adjoints, BEM and reduced
models are established broad ideas; the frontier is in particular formulations,
guarantees, hardware mappings and demonstrated regimes.

## Research admission and promotion

For every experiment retain the referenced version, bibliographic/access record,
independent derivation, model/discretization parameters, source rights, held-out
cases, hardware/precision, raw residual/conservation/error data and total cost.
An implementation must have a validated reference fallback and clear failure
states when that fallback is part of its acceptance contract. Report a heuristic
error indicator as such; claim a rigorous bound only under the theorem's actual
assumptions. No universal neural-operator/PINN, quantum-speedup or autonomous
physics-discovery claim is made by this plan.

Recheck the relevant literature when starting or materially changing a numerical
method, including new results and known failures. Record the search date and
source versions. Re-evaluate old and new methods on the same declared workloads.
This is a development rule, not a scheduled monitoring task.
