<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver accuracy benchmark program

Established 2026-10-12. This is the working register for benchmarking SPIKE's
solvers against independent analytical solutions, published numerical results,
separately installed programs, and measurements, then improving observed errors.
The [first executed baseline](validation/SOLVER_ACCURACY_BASELINE_20261012.md)
is deliberately scoped. All-family external accuracy qualification is incomplete.
The runtime authority remains [solver status](SOLVER_STATUS.md).

The [solver improvement action plan](SOLVER_IMPROVEMENT_ACTION_PLAN.md) turns
the executed findings into ordered implementation tasks, proposed acceptance
gates and a machine-readable backlog. Planned tasks do not promote solver status.

## Comparison rules

1. Freeze the case before running: geometry, units, materials, constitutive
   model, excitations, initial/boundary conditions, port/reference planes,
   sampling locations/times, and tolerances. Record reference revision/page/table,
   uncertainty, license, and applicability. A DOI alone is not an oracle.
2. Independently construct SPIKE fixtures. Follow CONTRIBUTING's clean-room
   rule; do not copy external implementations, example meshes, or test datasets.
   Admitting an external dataset requires explicit ownership and permitted-use
   review. Reading a publication does not authorize copying its assets.
3. Save original inputs, raw outputs, solver versions and binary hashes,
   relevant source hashes, host, settings, convergence and resource diagnostics.
   Record dirty-source state; a Git commit alone does not identify this workspace.
   Distinguish a new execution from a historical report.
4. Evaluate each observable separately. Use absolute error for zeros and
   temperature rise; relative error only with a declared meaningful scale.
   Compare complex S parameters in Cartesian form as well as magnitude/phase
   away from nulls. Compare waveforms at common physical times, never align away
   a delay error. No extrapolation, absent-value zero filling, or hidden exclusions.
5. Refine space and time independently over at least three relevant levels.
   Check iterative convergence and conservation before trusting error estimates.
   An error plateau can indicate model/port/boundary error. Apply Richardson/GCI
   only where its smoothness and asymptotic assumptions hold; oscillatory or
   non-asymptotic sequences remain inconclusive. See [NASA's guidance](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html).
6. Report `passed`, `failed`, `blocked`, `not_run`, and `unsupported` separately.
   Missing programs/reference data do not pass. Analytical consistency, cross-code
   agreement, measured correlation, and production qualification are separate axes.
   No global accuracy percentage or solver ranking from unlike cases.
7. Investigate failed cases with a minimal discriminating check. Fix only the
   implicated implementation or settings; keep original failing evidence and
   thresholds. Re-run matched comparisons and relevant regressions after changes.
   Numerical release changes still require knowledgeable human review.

## Coverage register

Rows group numerical families; they do not assert every registered workflow is
the same solver. Each concrete solver/backend/device/model needs its own case
binding. External adapter correctness is distinct from engine physics accuracy.
Comparator names below are targets unless executed evidence is identified.

| Family / current owners | Existing evidence | Next independent case and observables | Comparator targets and remaining gate |
| --- | --- | --- | --- |
| Routed DC, harness PI, PEEC R/L/C/G, PDN; `dc_solver`, `hybrid_dc_solver`, native PEEC | Trace/via/sheet resistance, Rosa/Grover self-L, shared-reference matrix; first baseline below | Independently authored straight/parallel conductors and coaxial/plate limits; R, self/mutual L, C matrix, impedance, current balance; mesh/frequency sweeps | FastHenry/FastCap or FEMM electrostatics for supported geometries, Q3D, measured coupons. Current C/G remains approximate; proximity and return-path limits must stay explicit. |
| Native linear MNA, owned SPIKES, nonlinear/compact models, switching converters | Nine shared scalar circuit cases passed against ngspice and LTspice; RC/RL refinement executed | Broaden to AC poles/phase, full transient histories, diode/BJT/MOS same-model I/V and charge, stiff switching and failure cases; KCL, energy, waveform errors | ngspice, LTspice, Xyce. Different device models are not a kernel comparison. Buck/RF/motor labels in current corpus are ideal electrical surrogates. |
| Uniform/coupled SI, harness MTL, network algebra | Analytic/modal/loaded-line checks; Cambridge measurement postprocessing is not prediction correlation | Independently authored uniform two/four-port lines; complex S, delay, Z0, crosstalk and TDR, then a matched measured coupon with calibration/de-embedding uncertainty | openEMS/EMerge, HFSS/CST/HyperLynx; measured VNA/TDR. Match terminals/reference planes and full geometry before comparing. |
| Solid thermal: lumped/board/layered, structured finite volume, tetrahedral FEM, transient | Scoped synthetic CalculiX slab/contact comparisons; analytical/manufactured/conservation checks | Layered slab with contact resistance, transient slab, convection/radiation; temperature rise, flux, energy and time/mesh error. Select NAFEMS cases only after boundary support is checked | CalculiX, MOOSE, COMSOL/ANSYS. Current synthetic checks do not qualify measured PCB/package temperatures. |
| Electrothermal/PWM and retained-volume coupling | Analytical energy/feedback and scoped CalculiX histories; historical failed correlations remain failed | Temperature-dependent resistor exact root, then matched PWM energy deposition/gathering and contact cases; V/I/T, energy and coupling-iteration error | ngspice/Xyce with equivalent thermal network; CalculiX for solids; COMSOL candidate. Match device physics and spatial heat maps. |
| Native cavity CFD, reduced internal airflow, laminar channel CHT | Native/SU2 Re=100 16/32/64 cavity comparison; analytic channel/CHT checks | Repeat cavity with velocity/vorticity profiles; channel pressure/flow and heat transfer. NASA backward-step measured case only on a turbulence-capable route | SU2, OpenFOAM, Fluent/COMSOL. Laminar native cavity cannot represent the NASA turbulent backward step. |
| External fan/enclosure CHT | OpenFOAM synthetic execution/mass/energy evidence; no second-code or measurement accuracy comparison | Heated plenum experiment: as-built geometry, inlet conditions, sensor temperatures and pressure drop; mesh/time/BC sensitivity | OpenFOAM/SU2 CHT, Fluent/Icepak/FloTHERM targets. Measurement admission and uncertainty review still required. |
| Full-wave/retained-volume EM, antenna and scattering adapters | Scoped openEMS patch and electrostatic retained-plate oracle; EMerge execution alone is not accuracy evidence | Retained plate C/E, cavity resonance and independently authored patch; S, resonant frequency, power balance, fields, efficiency. Vary interior mesh, PML and duration separately | openEMS, Palace/EMerge where supported, HFSS/CST/COMSOL. Native MoM/full-wave IDs remain unavailable; published Yagi exploration has unmatched conditions. |
| Planar magnetic FEM, eddy currents, machines, force/torque and 1-DOF actuator | Analytical/refinement/energy/coenergy checks only | Compatible planar linear/nonlinear magnetic circuit and conductor diffusion; B, flux linkage, inductance, losses and force versus coenergy derivative | FEMM/Elmer when runnable, Maxwell/COMSOL. Do not flatten a 3D TEAM case into a 2D qualification claim. |
| Physical optics / Optycal | One-way PEC integration only | Matched illuminated plate in the supported asymptotic regime; complex scattered field/angular response, normalization and distance sensitivity | Published analytical optics, CST/HFSS scattering targets. No absolute calibration or diffraction/shadowing qualification currently. |
| Battery, scalar co-simulation, digital twin | Synthetic analytical/model-identity checks only | Prescribed-current one-RC pulse response, held-out measured discharge; partitioned-versus-monolithic coupled ODE and timestep convergence | Independently derived ODE/reference integrator, equivalent circuit in ngspice; reviewed manufacturer/measurement data. Fitting and testing must use separate records. |
| General structural/thermomechanical and generic external FEM | No qualified general stress/deformation route; generic FEM manufactured tests and discovery contracts only | Future cantilever/displacement/thermal-expansion case only after a real matching solver route exists | CalculiX structural/ANSYS/COMSOL candidates; mark unsupported now. FreeCAD geometry exchange and actuator mechanics do not establish structural FEA. |

Coverage evidence is indexed by [subsystems](SUBSYSTEM_INDEX.md),
[handbook](SOLVER_HANDBOOK.md), and [research ledger](SOLVER_REFERENCES.md).
External versions and current acceptance must be taken from the actual run,
not the target names in this table.

## Published reference register

Reviewed primary pages on 2026-10-12; metadata review does not mean the associated
case was executed or its assets admitted. Existing method citations are retained
in SOLVER_REFERENCES rather than duplicated as claimed new discoveries.

| Reference | Intended use and admission state |
| --- | --- |
| [Rosa/Grover, NBS Bulletin, DOI 10.6028/bulletin.185](https://doi.org/10.6028/bulletin.185) | Existing self/mutual-inductance analytical lineage. Independently derive compatible conductor fixtures; self-L agreement alone does not validate the full L matrix. |
| [NASA NPARC spatial convergence](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html) | Richardson/GCI methodology and assumptions; not a physical dataset or universal acceptance tolerance. |
| [NASA Driver-Seegmiller backward step](https://tmbwg.github.io/turbmodels/backstep_val.html) | Published experimental Cf/Cp/velocity reference. Existing admitted Cf record is documented in CFD_PUBLIC_REFERENCE_CORPUS; matching SPIKE prediction remains not run. Preserve corrected Re and normalization. |
| [MOOSE NAFEMS T3 transient conduction](https://mooseframework.inl.gov/moose/modules/heat_transfer/nafems_t3_verif.html) | Candidate transient thermal verification with a published open-source result. Reconstruct the mathematical case independently; source data/assets are not imported. |
| [COMSOL 1D conduction/radiation verification](https://doc.comsol.com/6.4/doc/com.comsol.help.models.mph.heat_radiation_1d/heat_radiation_1d.html) | Candidate published commercial benchmark tied to NAFEMS; match exact radiation boundary and observable before adoption. No COMSOL run performed. |
| [NAFEMS vendor verification archive](https://www.nafems.org/community/vendor-network/code-verification-archived/) | Locate independently documented commercial verification cases; availability/redistribution and numerical tables require case-level review. |
| [NIST StRD usage](https://www.itl.nist.gov/div898/strd/general/howto.html) | Candidate reference for regression/fitting infrastructure only; certified fit agreement is not device-model physical validity. |
| [ngspice official documentation](https://ngspice.sourceforge.io/docs.html) | Pin circuit dialect/model/integration assumptions for live comparisons; not an independent physical accuracy oracle. |
| [FEMM official pyFEMM documentation](https://www.femm.info/doku/doku.php?do=&id=pyfemm) | Candidate bounded external magnetics adapter; independent original geometry/scripts required. No FEMM benchmark executed. |

The heated-plenum measurement candidate and its license/provenance review remain
in [the CFD corpus](CFD_PUBLIC_REFERENCE_CORPUS.md). No purchased software,
external asset redistribution, or third-party source adaptation is part of this baseline.

## Execution and improvement queue

The 13 October ACC01 signed-amplitude waveform sweep supersedes no historical
endpoint evidence: its stricter pointwise envelope fails at nonzero excitation,
including 1 mV and 1 uV. Error scales proportionally rather than flattening at a
floor. Independent recurrence reproduces the recorded startup/ramp-corner
backward-Euler defects, so endpoint agreement must not imply whole-waveform
qualification. Retain the unbundled local `acc01-20261013-rerun-1/report.json`
record as failed,
source-bound evidence; use [the action register](SOLVER_IMPROVEMENT_ACTION_PLAN.md)
for the integration/event discriminator and unchanged acceptance gates.

1. Preserve the first circuit/analytical baseline and timestep result. For the
   measured passive RC/RL endpoint, quartering the requested timestep reduces
   SPIKES error about sixteenfold; use that setting when this error budget matters.
   This is a verified settings improvement, not a new kernel capability.
2. Extend circuit comparisons to common-time waveform norms, maximum local error,
   AC phase/poles and supported nonlinear models. Pin the same integration controls
   where possible; otherwise report the settings difference and accuracy versus cost.
3. Repeat existing CalculiX, SU2 and retained-EM cases under the current artifact
   identities before extending to NAFEMS, magnetic and measured SI cases. Historical
   reports cannot certify newly changed sources or adapters.
4. Admit the first applicable thermal/flow and SI measurements with uncertainty
   and complete model setup. Execute predictions without tuning to held-out data.
5. Turn each reproducible failing accuracy case into a regression and a narrow
   improvement task. Promote only the demonstrated operating envelope after review.

Every new case record needs: ID/family/backend, source and permitted use,
model/setup equivalence, independent oracle, observable/unit/normalization,
predeclared error/conservation/convergence gates, runnable command, artifact
identities, actual status and exclusions. Until those are supplied, a candidate
in this register remains `not_run` rather than an established accuracy benchmark.
