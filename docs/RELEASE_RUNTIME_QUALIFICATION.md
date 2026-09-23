# Release Runtime Qualification

## Purpose

SPIKE must not publish a desktop package whose worker exposes a different
product capability set from the source worker used to create it. The
source-versus-packaged qualification gate is therefore a required Wave 0
release-evidence check. It is a deployment parity check, not numerical
validation and not a promotion of any solver status.

## Contracts And Inputs

| Item | Value |
|---|---|
| Qualification contract | `spike/release-runtime-qualification/v1` |
| Runtime snapshot contract | `spike/worker-runtime-snapshot/v1` |
| Source worker command | `<source-python> -m python.spike_core.service` |
| Packaged worker command | `<packaged-worker>` |
| Report artifact | `build/release-runtime-qualification.json` |
| Package manifest contract | `spike/packaged-worker-manifest/v2` |

The collector sends JSON-line requests for `health`, `capabilities`,
`capability_ledger`, `list_accelerators`, `list_external_engines`, and
`benchmarks`. It normalizes release-significant fields, records rejected
requests as `collection_errors`, hashes the canonical snapshots, and compares
eight required sections:

1. `collection_errors`
2. `health`
3. `product_capabilities`
4. `solver_plugins`
5. `capability_ledger`
6. `accelerators`
7. `external_engines`
8. `benchmarks`

## Commands

Run a standalone comparison against an already-built worker:

```powershell
.venv\Scripts\python.exe scripts\qualify_release_runtime.py `
  --source-python .venv\Scripts\python.exe `
  --packaged-worker app\src-tauri\resources\worker\spike-worker\spike-worker.exe `
  --output build\release-runtime-qualification.json
```

Build a worker using the pinned offline release environment. This invokes the
same parity gate before it writes the manifest:

```powershell
.venv\Scripts\python.exe scripts\build_packaged_worker.py
```

The build additionally requires packaged `health=ready`, a runnable native
`spike.peec_2_5d` plugin, and a clean permanent benchmark summary. Those
checks do not replace parity qualification.

## Current Recorded Evidence

The current evidence at `build/release-runtime-qualification.json` was
generated at `2026-08-24T16:54:55.646512+00:00` and is **passed**.

| Measure | Recorded value |
|---|---|
| Required checks | 8 |
| Passed checks | 8 |
| Failed checks | 0 |
| Matching sections | All eight required sections |
| Source snapshot digest | `0537e5dc7cd36cd59ac1be3d510a1df56f1edce77dffe7a7e30e0d682bf37906` |
| Packaged snapshot digest | `0537e5dc7cd36cd59ac1be3d510a1df56f1edce77dffe7a7e30e0d682bf37906` |

The packaged worker is launched with the repository/application root supplied
as `SPIKE_HOME`, so runtime discovery resolves the same managed external-engine
and validation assets as the source worker. Frozen-package acceleration
discovery also falls back to a module's `__version__` when distribution metadata
is absent. Regression tests cover both behaviors.

The packaged worker resource contains the matching qualification report and a
SHA-256 worker manifest. The current manifest also records a passing
`spike/packaged-arrow-probe/v1` transaction: the frozen executable writes a
package containing a canonical DesignIR-bound Arrow v4 table with two tracks,
one exact-boundary zone, and one per-layer-profile via. One retained unresolved
padstack occurrence is package-bound but excluded from the four copper rows.
The source reader verifies manifest identity, index, digest, byte-canonical
encoding, and exact decoded rows. This evidence proves release-significant runtime
parity for the collected contracts. It does not prove clean-machine packaging,
artifact signing, or numerical solver validity.

## Strict Advancement Rule

The runtime-parity portion of Wave 0 is closed only while a freshly generated
qualification report remains `passed`, all eight required checks pass, neither
snapshot contains `collection_errors`, and the matching report accompanies the
package manifest. Any packaged-worker or discovery change must regenerate this
evidence.

A parity pass still does not make a solver validated. Numerical release gates
remain the analytical, convergence, independent-reference, and measured-board
requirements in `docs/VALIDATION_PROGRAM.md` and the Wave 0 matrix.
