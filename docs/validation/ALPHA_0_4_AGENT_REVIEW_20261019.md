<!-- SPDX-License-Identifier: Apache-2.0 -->
# 0.4 alpha bounded numerical agent review, 2026-10-19

This is an independent AI review supporting the release candidate. It is not the
knowledgeable human numerical review required by CONTRIBUTING.md. Human review
and independent physical qualification remain pending. No new actionable numerical
defect was confirmed in the bounded scope below.

## Source scope

The following production files were reviewed and byte-matched against candidate
`591e97f103ec9068fe0595aa0c31ec0732b39615`:

- `python/spike_core/rlgc_line_network.py`
- `python/spike_core/rlgc_line_fields.py`
- `python/spike_core/rlgc_line_cascade.py`
- `python/spike_core/rlgc_line_junction.py`
- `python/spike_core/hybrid_mesh.py`
- `src/spikes/transient_solver.cpp`
- `src/spikes/transient_session.cpp`

Review covered supplied RLGC formulations and contracts, Radau IIA3 stages,
capacitor currents, initial/topology rejection, breakpoint/session handling and
the mesh via-bore correction. It did not exhaustively review every solver.

Supplementary inspection covered the unchanged published-base thermal and
filled-boundary implementations: `assembly_tetra_transient.py`,
`assembly_field_transient.py`, `retained_thermal_step.py`,
`transient_resistive_electrothermal.py`, `source_filled_boundary.py`,
`filled_copper_path.py`, `via_transition_geometry.py` and
`src/peec/via_transition_mesh_input.cpp`. Python paths are under
`python/spike_core/`. Unchanged means relative to published base `dc3cdc83`.

## Executed evidence

The original development checkout, using its qualification Python 3.11.9:

```text
python -m unittest tests.python.test_rlgc_line_network tests.python.test_rlgc_line_fields tests.python.test_rlgc_line_cascade tests.python.test_rlgc_line_junction tests.python.test_assembly_tetra_transient tests.python.test_transient_resistive_electrothermal -q
python -m unittest tests.python.test_hybrid_mesh_containment tests.python.test_rlgc_line_network_contract tests.python.test_rlgc_line_fields_contract tests.python.test_rlgc_line_cascade_contract tests.python.test_rlgc_line_junction_contract -q
```

These passed 74 and 28 tests respectively. The retained
`build-peec-native/test_spikes_transient.exe` passed too; this review execution
was not a fresh candidate build. Fresh candidate C++ build/CTest evidence is
recorded separately in the alpha readiness record.

The candidate follow-up executed both unchanged exact tests:

```text
python -m unittest tests.python.test_cli.SpikeCliTests.test_pi_release_qualification_runs_current_benchmarks_when_report_is_omitted tests.python.test_field_circuit_cosim.FieldCircuitCosimulationTests.test_release_owned_spice_engine_executes_inside_field_iteration -v
```

Both passed in 29.222 seconds with the freshly built candidate C API library and
CPython 3.11 PEEC binding, Python 3.11.9 and writable temporary storage. The initial
Python 3.12 CLI run lacked a matching PEEC extension: 11 benchmarks passed and four
were skipped. Supplying the correct native runtime resolved these prerequisite
failures without modifying numerical sources or assertions.

| Fresh candidate artifact | SHA-256 |
| --- | --- |
| `spike_peec_native.cp311-win_amd64.pyd` | `7608bc48379ee2227d358a831d5c5a75ef678fbd7b0cd69af5f2febc4c6bb224` |
| `spikes_c_api.dll` | `5df4883faaa74d7930c5094d31ff6139efd07b5e73626e5a7c8125e082ffbb0a` |

Detailed local-only evidence, not included as downloadable checkout files, is
retained under `.local/release-0.4/`: `numerical-review-exact-tests-py311.log`,
`numerical-review-native-environment.log`, `numerical-review-cli-rerun.log` and
`numerical-review-benchmark-report.json`.

## Remaining limits

The ACC01 receipt's numerical C++ hashes match, but its recorded
`python/spikes/native_runner.py` hash differs. That receipt cannot establish
complete candidate provenance. Actual-board EBrake/Marble PI/SI limitations remain
as documented in [board readiness](BOARD_PISI_READINESS_20261019.md).
This review does not establish production suitability, full multiphysics
qualification, or a completed human approval gate.
