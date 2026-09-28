<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# SPIKE solver handbook

Documentation audit: 2026-09-20. This is the entry point for solver users,
developers and numerical reviewers. It connects governing models, code,
verification and research provenance; it is not a new capability declaration.

## Read this first

1. [Solver status](SOLVER_STATUS.md): what is executable and its validity tier.
2. This handbook: how the model families fit together and what their results mean.
3. [Research references](SOLVER_REFERENCES.md): source identity, recorded use and limits.
4. [Validation program](VALIDATION_PROGRAM.md) and [PI release gates](PI_RELEASE_QUALIFICATION.md): what evidence is required for promotion.
5. [CLI workflow](CLI_WORKFLOW.md) or [SI workflow](SI_WORKFLOW.md): how to run a study.

The public SPIKE application/adapter and the separately maintained native SPIKES
multiphysics repository are not interchangeable. Private native research and
formulations remain in that repository's `docs/RESEARCH_BASE.md` and
`docs/formulations/`; they are not copied into this public handbook. Native
research prototypes do not automatically become advertised application physics.

## Runtime and model boundaries

EDA input enters through an importer and becomes DesignIR. AnalysisSpec binds
geometry, nets, terminals, materials, resources and the study. The solver
registry selects a declared capability. Results include issues, provenance and
validity state, rather than only plots. The UI does not invent missing fields.
See [architecture](../ARCHITECTURE.md), [contracts](CONTRACTS.md),
[subsystems](SUBSYSTEM_INDEX.md) and [solver plugins](SOLVER_PLUGIN_ARCHITECTURE.md).

Use SI units in governing equations. PCB coordinates may enter in mm; conversions
must occur at the documented boundary, not by adjusting a material constant.
Specify port ordering, current/voltage polarity, return conductor, reference
impedance and reference plane. Shared net names are not proof of physical bonds.

## Method and implementation map

The equations below explain the model families. They do not assert that every
term, boundary condition or geometry is available in every backend.

| Model family | Governing model and numerical approach | Implementation and verification entry points | Limits and reading |
|---|---|---|---|
| Routed DC / PI | Ohm law, R = length/(conductivity * area), nodal current balance; finite-volume spreading for admitted zones | [DC guide](DC_SOLVER.md), [benchmarks](../python/spike_core/benchmarks.py) | Contacts, terminals and zone convergence matter; not AC. |
| Native PEEC / broadband PI | Partial inductance plus RLCG/network assembly; frequency-domain branch terms include R(omega) + j*omega*L | [native kernel](../src/peec/peec_solver.cpp), [adapter](../python/spike_core/peec_plugin.py), [native tests](../tests/test_peec.cpp) | Experimental quasi-static approximation; not full-wave radiation. [R1-R3](SOLVER_REFERENCES.md#conductor-and-network-methods). |
| Circuit / transient PI | Modified nodal residuals; supported nonlinear device residual/Jacobian stamps; time-discretized circuit state | [native MNA](../python/spike_core/native_mna.py), [circuit core](../src/spikes/dc_solver.cpp), [transient core](../src/spikes/transient_solver.cpp), [wave 3](SPIKES_LANGUAGE_ANALYSIS_WAVE3.md), [wave 4](SPIKES_LANGUAGE_ANALYSIS_WAVE4.md) | Supported language/device subsets, not arbitrary SPICE/IBIS compatibility. No paper-level lineage is invented where absent. |
| Uniform / coupled SI channels | dV/dz = -(R+j*omega*L)I; dI/dz = -(G+j*omega*C)V with per-unit-length matrices and explicit terminations | [uniform channel](../python/spike_core/si_channel.py), [coupled channel](../python/spike_core/si_coupled_channel.py), [geometry guide](GEOMETRY_DERIVED_SI_CHANNEL.md) | Bounded quasi-TEM extraction, not arbitrary discontinuities or broadband full-wave PCB extraction. [R4-R6](SOLVER_REFERENCES.md#conductor-and-network-methods). |
| Multiport / multiboard networks | Internal wave elimination: S_eff = S_ee + S_ei (I-C*S_ii)^-1 C*S_ie; implement a linear solve, not explicit inversion | [graph implementation](../python/spike_core/si_network_graph.py), [network increment](SI_NETWORK_GRAPH_INCREMENT_20260907.md) | C connects declared internal pairs at common reference planes. Connectors/returns must already be modeled; not cross-board field extraction. |
| Waveforms, eyes, BER estimates | LTI convolution, explicit source/load models and sampled receiver statistics | [SI workflow](../python/spike_core/si_workflow.py), [PAM4](../python/spike_core/si_pam4_eye.py), [finite-record correction](SI_FIELD_RELIABILITY_20260920.md) | PAM4 uses fixed/ideal phase selection, training DFE and Gaussian BER proxies; not dynamic CDR or Ethernet compliance. [R7-R8](SOLVER_REFERENCES.md#formats-and-measurement-practice). |
| Resonance / Q | Declared RLC fit and half-power checks; isolated free-decay mode u ~ exp(-alpha*t) cos(2*pi*f*t+phi), Q = pi*f/alpha | [RLC fitting](../python/spike_core/si_resonance.py), [AR(2) ringdown](../python/spike_core/si_ringdown.py), [modal evidence](CROSSBOARD_FIELD_MODE_INCREMENT_20260907.md) | Network peaks are not automatically physical modes; fitted Q includes admitted loading/loss and is not general eigenmode qualification. [R9](SOLVER_REFERENCES.md#resonance-and-external-fields). |
| External RF / EMI reference | Maxwell FDTD through installed openEMS; independent port excitations and full incident/reflected wave normalization S*A = B | [four-port runner](../scripts/run_crossboard_openems.py), [normalization](../python/spike_core/multi_excitation_network.py), [screens](../python/spike_core/crossboard_field_screen.py) | Explicit box benchmark; PML, duration, mesh, reference planes and material loss need qualification. [R10](SOLVER_REFERENCES.md#resonance-and-external-fields). |
| Solid thermal / electrothermal | rho*c_p*dT/dt = div(k grad T)+q; harmonic face conductance, implicit Euler, optional interface resistance and Picard radiation; electrical heat feedback in admitted coupling | [thermal solver](../python/spike_core/structured_solid_thermal.py), [electrothermal](../python/spike_core/structured_electrothermal.py), [priority guide](NATIVE_THERMAL_PI_SI_PRIORITY.md) | Structured finite volumes and bounded coupling; not arbitrary conforming geometry or general transient semiconductor electrothermal signoff. |
| Laminar CHT / external enclosure CFD | Steady developed plane-channel flow and finite-volume energy; optional OpenFOAM workflows have separate model/BC requirements | [laminar solver](../python/spike_core/laminar_channel_cht.py), [CHT guide](BOUNDED_CHT_AND_RADIATION.md), [fan qualification](FAN_CHT_QUALIFICATION.md) | Channel solution is not arbitrary enclosure/turbulence validation. [R11-R12](SOLVER_REFERENCES.md#thermal-and-flow). |
| Mesh / MoM groundwork | Exact-grid predicates and constrained planar triangulation; separate surface basis and CAD-mesher integration | [native topology](../src/geometry/planar_topology.cpp), [triangulation](../src/geometry/constrained_triangulation.cpp), [surface basis](../python/spike_core/mom_surface_basis.py), [OCC mesh](OCC_CONFORMING_PCB_MESH.md) | A valid surface basis or closed mesh is not an EFIE/MFIE/CFIE solver. See [R13-R16](SOLVER_REFERENCES.md#geometry-and-meshing). |

Full optics, general actuator force/torque and private Maxwell research must be
checked against their own formulation and runtime manifests. This handbook does
not infer them from a generic FEM backend, magnetic-field variable or registry entry.

## How to interpret numerical evidence

- **Analytical verification:** compare with an independently derived solution
  within the same assumptions; include units and predetermined tolerances.
- **Discretization convergence:** refine all relevant feature scales. Changing
  only the bulk mesh is insufficient if substrate, copper or ports stay fixed.
  Hold physical PML position fixed while testing interior refinement; test PML
  and time-window sensitivity separately.
- **Independent-solver comparison:** match geometry, material, sources, loads,
  reference planes and normalization. Agreement may share modeling errors.
- **Measured correlation:** match the physical experiment and uncertainty model.
  Admission of a measurement file is not a successful prediction.
- **Production qualification:** adds supported platforms, resource/cancellation,
  packaged/native parity, repeatability, offline installation and review gates.

Conservation depends on the study: current/source balance, nonnegative stored
energy, passive-network singular-value checks under the specified wave convention,
or thermal input minus output minus stored-energy change. Reciprocity is not a
universal requirement for nonreciprocal devices. Finite-band causality/passivity
screens are not proofs over all frequencies or termination conditions.

Never zero-fill absent measured S-parameters, report directivity as realized gain,
equate an RLC fit with an eigenmode, or label a corpus import as a solved board.
Do not change acceptance thresholds after seeing results merely to pass a gate.

## Current reproducible evidence

| Record | What it establishes | What it does not establish |
|---|---|---|
| [2026-09-20 software repair](QUALIFICATION_REPAIR_20260920.md) | 1,724 Python tests without failures/errors in the documented CPython 3.11 environment; two named skips; 15 benchmarks and five native tests pass | Other Python binaries, all operating systems, all physics or a release certificate |
| [SI/field reliability](SI_FIELD_RELIABILITY_20260920.md) | PAM4 finite-record regression and actual four-excitation coarse field run with positive decay evidence | Refined-grid physical qualification; the old three-grid screen failed |
| [Cambridge wire data](MEASURED_SI_CAMBRIDGE.md) | Measured file admission and bounded network processing | Complete measured four-port matrix or PCB field correlation |
| [NBS Yagi](NBS_YAGI_COMPARISON.md) | Exploratory solver/measurement discrepancy with explicit geometry differences | Geometry-matched uncertainty-qualified antenna validation |
| [CFD references](CFD_PUBLIC_REFERENCE_CORPUS.md) | Admitted/selected public experimental sources with distinct status | Executed general enclosure correlation |
| [CERN / Marble](CERN_MARBLE_EVALUATION_20260920.md) | Pinned hardware fixtures and actual import/conversion findings | Measured SI/PI signoff, conversion completeness or fabrication approval |

Use [solver environment preflight](../scripts/check_solver_qualification_environment.py)
before the suite; the commands and native artifact identity are in the repair
record. Generated `build/` evidence may not exist on another checkout: retain
inputs, hashes, runtime identity and command lines or regenerate it. Do not
silently substitute a synthetic result when an external runtime is unavailable.

## Research and documentation maintenance

Every new method should record: source ID and exact revision; what was learned;
the independent derivation; code and contract; valid geometry/material/frequency
domain; complexity/resource bounds; analytic oracle; convergence evidence;
independent/measured comparison; licensing status; and remaining gates.

The [reference guide](SOLVER_REFERENCES.md) is curated. The generated
[reference inventory](generated/solver-reference-inventory.json) is deliberately
broader: it preserves recorded URLs/DOIs and file/line occurrences, including
non-paper links and test literals. It does not claim every link influenced an
algorithm. Refresh with `python scripts/index_solver_references.py`; use
`--check` to detect drift. It does not scan the private repository or download
papers. Sources mentioned only in unavailable past chats cannot be recovered
reliably and must not be fabricated.
