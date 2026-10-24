# Solver performance coverage audit — 23 October 2026

## Scope and interpretation

The subsequent [analysis/loading pass](ANALYSIS_LOADING_PERFORMANCE_20261023.md)
adds measured project opening, repeated-design multiboard preparation and
retained-tetrahedral CFD/CHT improvements. Its linked final reports supersede
early speed estimates where integrity hardening added necessary checks. The
historical family inventory below remains workload-specific evidence, not a
claim that every family has been optimized or qualified.

This is a read-only evidence audit of active solver families, their existing
benchmark entry points, and retained timing evidence. No solver, stress, large
board, external-engine, or native workload was executed for this audit because
the host had about 2.57 GB free RAM. The audit does not turn a correctness
benchmark into a performance qualification and does not infer a universal
millisecond target from a small synthetic case.

The inventory follows [`SUBSYSTEM_INDEX.md`](../SUBSYSTEM_INDEX.md) and the
capability boundaries in [`SOLVER_STATUS.md`](../SOLVER_STATUS.md). "Measured"
below means a retained artifact records wall time for a named input and runtime.
It does not mean production-qualified, cross-machine representative, or fast
enough for interactive use. The ten cases in
[`solver-benchmarks.json`](solver-benchmarks.json) are numerical correctness
checks and contain no solve timing, so they provide no performance evidence.

## Coverage matrix

| Active family | Status boundary | Existing benchmark entry points | Retained performance evidence | Coverage judgment |
|---|---|---|---|---|
| Routed-copper DC, hybrid DC, native PEEC RLCG and PEEC transient | Operational or experimental according to the particular geometry/mode; original EBrake density and AC gates remain open | `scripts/benchmark_pi_finite_contact.py`, `scripts/benchmark_pcb_mesher.py`, `scripts/benchmark_circuit_timestep_accuracy.py`; correctness in `docs/validation/solver-benchmarks.json` | The retained Arduino mesher comparison reports 1.039631 s warm median and 2.228842 s cold wall median after optimization. The same artifact records 10- and 20-occurrence preparation at 11.148 s and 21.507 s (about 1.11/1.08 s per occurrence). Marble's complete repaired project-runtime mesh took 215.794 s, while its incomplete historical baseline is not comparable. | **Known preparation bottleneck; solve latency unqualified.** Meshing has useful phase evidence, but no common retained end-to-end DC/PEEC latency series by nodes, branches, ports, frequencies, and backend. |
| Native linear MNA, owned circuit kernel, SPICE/ngspice staging and converter studies | Native linear RLC/MNA and bounded owned-kernel paths execute; nonlinear/general SPICE and hybrid capabilities retain their documented gates | `scripts/benchmark_circuit_timestep_accuracy.py`, `scripts/run_spikes_wave1_benchmarks.py`, `scripts/run_spikes_competitive_benchmarks.py`, `scripts/benchmark_spikes_native_smps.py`, native `spikes_behavioral_speed_test` | [`artifacts/spikes-native-smps-speed-20261013.json`](../../artifacts/spikes-native-smps-speed-20261013.json) records warm end-to-end medians of 0.481 ms for 401 points and 6.799 ms for 10,000 points through bulk native transport. It explicitly excludes cold startup and switching solve. Timestep benchmarks primarily qualify accuracy, not general runtime. | **One narrow fast path measured; broad family unknown.** There is no retained cold-worker, parse/compile, nonlinear ngspice, topology-size, transient-step, or converter end-to-end scaling matrix. |
| SI sampled networks, loaded N-port response, RLGC lines/cascades/stars, crosstalk and PAM3/CDR references | Mostly bounded experimental supplied-network workflows; geometry extraction and measured board qualification remain open | `scripts/benchmark_si_loaded_response.py`, `benchmark_si_impedance.py`, `benchmark_si_crosstalk.py`, `benchmark_si_multiboard.py`, `benchmark_si_network_graph.py`, `benchmark_si_network_graph_workflow.py`, `benchmark_si_pam3.py`, `benchmark_si_transition_pi_cdr.py`, `benchmark_cambridge_measured_si.py` | [`loaded-response-benchmark.json`](../../artifacts/cli-validation-20260907/si/loaded-response-benchmark.json) records equivalent batch-128 medians of 1.767 ms for 1,025 frequencies and 7.359 ms for 4,097 frequencies on a four-port/three-RHS synthetic case. Native transition-PI/CDR and interface documents retain additional isolated kernel timings, but not one common end-to-end boundary. | **Kernel coverage is comparatively good; workflow coverage is fragmented.** Import, network preparation, graph composition, worker serialization, and UI result delivery are not timed together on representative multi-board requests. |
| Compact, board/layered, component, tetrahedral and coupled thermal | Compact and several internal thermal paths execute; retained-volume and external comparisons remain experimental and case-bound | `scripts/benchmark_thermal_coupling_accuracy.py`, `scripts/benchmark_enclosure_cht.py`, `scripts/benchmark_enclosure_cht_v2.py`, `scripts/benchmark_su2_cht.py` | [`thermal_benchmark_summary.json`](../../output/solver-comprehensive-20261012/thermal/thermal_benchmark_summary.json) records 203 ms median for a tiny 16-node/12-tetra internal steady electrothermal fixed-point case. Its synthetic transient internal-plus-CalculiX core run took 14.466 s; individual CalculiX executions span roughly 0.266–2.345 s. These are single-host synthetic cases and are not retained STEP import/meshing timings. | **Seconds-scale external/coupled evidence exists, but phase attribution and scaling are weak.** Compact/component and realistic board/layered thermal lack a shared size sweep and cold/warm worker split. |
| Internal CFD/CHT and bounded enclosure flow | Experimental mathematical verification; general CAD CFD, turbulence, rotors, compressible flow, and production qualification remain gated | `scripts/benchmark_enclosure_prerequisites.py`, `benchmark_enclosure_cht.py`, `benchmark_enclosure_cht_v2.py`, `benchmark_cfd_capability_increment.py`, `benchmark_cad_cfd_open_flow.py` | The retained laminar-method record reports approximately 0.021/0.269/2.944 s for its three diagnostic sizes. CHT records contain case wall times, but explicitly reject portable speed claims. | **Measured only as isolated verification cases.** No standardized cells/unknowns/iterations/residuals-to-time scaling, peak-memory series, or interactive end-to-end target exists. |
| External CFD/thermal/structural and EM engines (SU2, OpenFOAM, CalculiX, Elmer, openEMS, EMerge, sparseLizard) | Discovery, adapters, and qualification differ per engine; detection is not execution readiness and several paths remain unvalidated | `scripts/benchmark_su2_airflow.py`, `benchmark_su2_cht.py`, `benchmark_cad_cfd_open_flow.py`, external portions of `benchmark_thermal_coupling_accuracy.py`, extension-specific openEMS tests/benchmarks | CalculiX has the bounded timings above. Other retained artifacts primarily establish execution, parity, or numerical evidence; they do not form a comparable performance corpus. | **Unqualified.** Process startup, case writing, meshing, solver iterations, parsing, and result transfer need separate clocks before considering persistence or caching. A blanket millisecond objective is incompatible with these subprocess and field-solve workloads. |
| Retained assembly EM and reduced multiboard circuit/thermal/magnetic models | Experimental; retained assembly EM summary explicitly says unvalidated | `scripts/run_retained_assembly_em_benchmark.py`, `scripts/benchmark_si_multiboard.py`, `scripts/benchmark_si_network_graph_workflow.py` | [`output/retained-assembly-em-benchmark-20261011/summary.json`](../../output/retained-assembly-em-benchmark-20261011/summary.json) records execution identity but status `unvalidated`; it is not admissible performance qualification. Multi-board timing is otherwise dominated by separately measured geometry preparation. | **Unknown/unqualified.** No representative 10/20-board solve-time and memory plateau exists; the prepared large-board workload is intentionally deferred until the memory start gate is met. |
| General fixed-grid co-simulation | Experimental orchestration across admitted participants; adapter physics retain their own status | `scripts/benchmark_cosimulation_overhead.py` | For two gain participants and 10,000 steps, Python 3.11 retained medians changed from 385.168 ms to 35.563 ms in [`cosimulation-before-py311.json`](../../output/performance-20261023/cosimulation-before-py311.json) and [`cosimulation-after-py311.json`](../../output/performance-20261023/cosimulation-after-py311.json), with identical request identity. This measures orchestration only, about 3.56 microseconds per step after the change. | **Orchestration microbenchmark covered; real coupling unknown.** Adapter execution, convergence iterations, field transfer, rejected steps, subprocesses, and result transport are absent. |
| Firmware/electrical behavioral and peripheral co-simulation | Bounded experimental owned-native modes; not MCU cycle or hardware timing qualification | Native `spikes_behavioral_speed_test`, `tests/cpp/test_spikes_peripheral_timing.cpp`; circuit/co-simulation benchmarks above | The peripheral validation suite took 61.551 s for four live tests, but that is suite duration rather than a stable per-step benchmark. Behavioral evaluator output reports controlled legacy/optimized trials when built and run, but no current cross-family latency contract exists. | **Insufficient for product latency claims.** Separate emulation, event-barrier, electrical solve, and transport timing is required. |
| Static thermoelasticity, planar magnetic machines/actuators, reduced EM machines and propulsion-machine coupling | Experimental bounded tetrahedral mechanics, planar P1 fields, supplied-parameter machines, and synthetic propulsion coupling; no general moving 3D machine, nonlinear material, fatigue, or production qualification | `scripts/benchmark_si_magnetic_accuracy.py`; manufactured/refinement and coupling checks referenced by `COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md`, `MAGNETIC_MACHINE_STUDIES.md`, and `validation/PROPULSION_POD_COUPLING_DERIVATION_20261023.md` | Retained records establish equations, refinement, energy, reciprocity, and coupling behavior. They do not retain a comparable solve-time distribution or problem-size/memory scaling series. | **No usable performance qualification.** Time mesh preparation, factorization/reuse, angle or timestep loops, coupling iterations, and result construction separately before selecting an optimization. |
| TCAD equilibrium, battery reference, equation devices and ideal analytical SMPS | Experimental, supplied-input reference capabilities with narrow mathematical scope | Native TCAD correctness test; `scripts/benchmark_spikes_native_smps.py`; model-specific analytical/regression suites | The ideal SMPS bulk-transport measurements are listed with the circuit family above. TCAD, battery, and equation-device records provide correctness rather than latency evidence. | **Mostly unknown.** Do not transfer the ideal SMPS timing to nonlinear transient devices, PDK/ngspice runs, battery horizons, or TCAD size scaling. |
| Internal optics and charged-particle reference kernels | Internal reference capabilities only; no general public optics/particle workflow or physical qualification | Native correctness executables (`test_native_optics_reference`, `test_native_particle_reference`) | Retained evidence counts correctness checks, not representative latency or scaling. | **No performance coverage.** Establish workload axes and public execution boundary before optimizing. |

## Evidence-backed priorities

1. **Instrument and reduce retained-board preparation first.** It is the clearest
   measured user-scale cost: about 1.04 s for one retained Arduino preparation,
   about 11.1/21.5 s for 10/20 occurrences, and 215.8 s for the complete Marble
   project-runtime mesh. Add phase clocks and allocation/peak-memory fields around
   source admission, topology/index construction, cell allocation, certification,
   and serialization. Then profile the largest phase and preserve exact mesh and
   completeness hashes. Reuse across identical immutable board designs is the
   first hypothesis worth testing; distinct boards require separate evidence.

2. **Create one shared end-to-end timing envelope at the worker boundary.** For
   each runnable family, retain cold start, warm validation/preparation, assembly,
   solve, postprocessing, serialization, and total time, plus problem-size axes
   and peak memory. Current scripts use incompatible boundaries, which prevents
   identifying whether Python validation, sparse factorization, external process
   startup, or result transport is the next bottleneck. Start with routed DC/PEEC,
   native MNA/transient, board thermal, enclosure CFD/CHT, and one external engine.

3. **Extend the co-simulation benchmark with real bounded participants before
   optimizing again.** The scalar orchestration case is already 35.6 ms for
   10,000 steps, so it no longer demonstrates a product bottleneck. Add one
   in-process circuit-plus-thermal case and one process-backed admitted adapter;
   report participant time, transfer/copy time, convergence iterations, rejected
   steps, and total. Preserve the current gain case as the orchestration floor.

4. **Measure external-engine startup separately from solve work.** Seconds-scale
   CalculiX evidence and external adapter architecture make a universal
   millisecond response unrealistic. A cold/warm decomposition can support
   safe case-cache or persistent-process proposals, but only after input/runtime
   digest, cancellation, isolation, and result-identity behavior are measured.

5. **Do not spend the next optimization pass on loaded SI algebra or native SMPS
   transport without a larger workflow trace.** Their retained warm medians are
   already single-digit milliseconds for the named cases. Import, preparation,
   worker transport, and presentation are more plausible end-to-end costs, but
   that remains a hypothesis until measured under the shared envelope.

## Limitations and qualification gaps

- Timings come from different dates, Python/native builds, machines, warmup
  policies, validation boundaries, and problem sizes. Ratios cannot be combined.
- Most numerical benchmark scripts prove accuracy, conservation, or execution;
  they do not report runtime distributions or memory.
- Small synthetic cases do not predict retained-board, CAD, nonlinear,
  turbulence, high-frequency, or external-engine behavior.
- A UI action has additional import, worker startup, IPC, normalization, result
  persistence, and rendering costs. Solver-only time cannot qualify UI latency.
- Milliseconds are plausible for cached presentation and selected small kernels.
  Meshing, large sparse solves, iterative multiphysics, and external processes
  require workload-specific targets and progress/cancellation behavior.
- No new evidence was generated during this audit. All numbers above are copied
  from retained repository artifacts and retain those artifacts' stated limits.
