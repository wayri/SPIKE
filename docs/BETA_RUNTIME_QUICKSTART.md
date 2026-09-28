<!-- SPDX-License-Identifier: Apache-2.0 -->

# Beta runtime quickstart

The SPIKE desktop/CLI is version 0.3.0 (engineering preview). The separately
versioned SPIKES circuit engine is 0.3.0-beta.1. Neither version promotes a
capability or qualifies a physics workflow. Their process adapters intentionally
report independent readiness states.

## Check this checkout

From the repository root:

```powershell
python scripts/run_beta_process_smoke.py
```

For a package gate that requires the bundled structured-circuit worker:

```powershell
python scripts/run_beta_process_smoke.py --require-circuit-worker
```

To inspect an explicitly installed private verification runtime without
granting it product eligibility:

```powershell
python scripts/run_beta_process_smoke.py --native-solver C:\absolute\path\spike-native-solver.exe --require-native-runtime
```

The command emits `spike/beta-runtime-readiness/v1`. A passing default report
means the public process declarations are self-consistent and every present
circuit package file passed its recorded size and SHA-256 check. It does not
mean a solver is accurate for an arbitrary PCB.

## Current boundary

| Component | Beta state | Runnable scope |
|---|---|---|
| Layout scoring | Experimental, available from source | Validate candidates, negotiate evidence, prepare native jobs, correlate results and compute scores. It does not route, place, mesh, or solve. |
| Circuit worker | Experimental when packaged and integrity-admitted | Reviewed structured workspace only. Raw netlists, arbitrary SPICE and public IBIS execution are not accepted. Trusted host supervision is required. |
| Native solver adapter | `integration_pending` | Probe and self-test plus separately declared verification workloads. Public PCB physics remains ineligible. |

Run the executable examples after the smoke probe:

```powershell
python examples/layout_scoring/run_examples.py
python examples/circuit_worker/run_examples.py
```

Use `python scripts/run_beta_process_smoke.py --help` for all gate options.
Production promotion still requires clean-machine packaging, private CI,
platform/MPI qualification, dependency approval and numerical correlation.
