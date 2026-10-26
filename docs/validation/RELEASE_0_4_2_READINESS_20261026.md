<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE 0.4.2 release readiness assessment - 26 October 2026

## Decision and scope

**Stable publication is not yet supported by the retained evidence.** Continue
preparing a local 0.4.2 candidate with the existing alpha/experimental capability
labels. Application version 0.4.2 and a successful installer build do not imply
stable qualification. This assessment does not approve publication, change a
solver gate, or relabel the separate installed 0.4.2-beta.

This is a program-wide assessment by subsystem and release acceptance gate,
using the ownership index, capability records, implementation of release guards,
retained test logs and bounded executed checks. It is not a line-by-line source
audit, new physical validation, full penetration test, or exhaustive manual GUI
acceptance. No numerical implementation was modified.

The inspected checkout had HEAD
`537023f84e70ed0d45915c7ef2b5cdb858d18228` and 3,585 Git status entries,
including 2,465 untracked entries, during inspection. These counts are a
point-in-time inventory, not a frozen-source identity; other authorized work
was ongoing. HEAD alone cannot identify this candidate. Preserve all existing
work and freeze the complete selected source before the final acceptance run.

Policies reviewed: [contribution gates](../../CONTRIBUTING.md),
[architecture](../../ARCHITECTURE.md), [design](../DESIGN_PRINCIPLES.md),
[language ownership](../LANGUAGE_POLICY.md), [engineering governance](../ENGINEERING_GOVERNANCE.md),
[publication identity](../ATTRIBUTION_POLICY.md),
[release plan](../RELEASE_0_4_2_PLAN.md), and
[platform scope](../MULTIPHYSICS_PLATFORM_STRATEGY.md).

## Findings in priority order

1. **Blocking: no passing full required suite bound to final source.** The
   retained Python run is 5,728 tests, 2 failures, 5 errors and 87 skips. It ran
   while source changed and predates subsequent geometry work. Its SHA-256 is
   `d6371fe8bca5294b463c97d38867ce89f9a81b08750dc42a30a644dd5f63862c`.
   The [integration audit](LATEST_SOLVER_INTEGRATION_20261026.md) records exact
   failed cases. Focused reruns can diagnose those cases but cannot convert
   that run into a passing final-source acceptance run. Review every skip's
   applicability to the supported package; do not call skipped dependencies
   qualified.
2. **Blocking: current SI08-S05 native acceptance is stale.** Three backlog
   tests reach the same `Stale native evidence validator` rejection. The
   detailed source audit below demonstrates additional drift beyond the first
   rejected hash. Keep historical receipts unchanged and regenerate actual
   current-source evidence before claiming completion for the new candidate.
3. **Blocking: numerical release review and remaining capability gates.**
   Knowledgeable human review of numerical changes remains required. IBIS
   voltage refinement at three probes, detailed polygon-prism CAD CHT timeout,
   source-specific mesh/time convergence and broader measured correlation are
   open as described by the candidate and owning method records. Experimental
   modes may retain their explicit limits; their availability must not be
   advertised as general validated engineering capability. No reviewer approval
   is inferred from automated checks.
4. **Blocking for claimed platform support: final artifact lifecycle evidence.**
   Final-source Windows clean-machine/offline launch, upgrade, reinstall and
   uninstall, native supported-size interaction and save/reopen must be retained.
   Earlier beta evidence and the worker/frontend candidate do not establish
   final-installer acceptance. Linux requires fresh version/source-bound
   qualification. The [0.4.1 Unix record](UNIX_RELEASE_041_20261024.md) reports
   macOS execution blocked by its hard 4 GiB address-space contract; successful
   rejection-path tests did not qualify macOS circuit execution. Do not silently
   relax that resource policy or claim all-platform delivery from a Windows build.
5. **Packaging input gap on this checkout:** the default Windows input guard
   rejects `No exact wheel bytes match jsonschema==4.25.1`. It searched its
   default historical wheel directories. Run it against the installer builder's
   actual retained build/runtime wheel directories and preserve the passing
   result. This observation does not prove a defect in a separately built worker.
6. **Fixed minor release guard gap:** application version checking omitted the
   owned Cargo lockfile package, leaving a documented manual step. The guard now
   requires exactly one local application entry matching the application version;
   missing, stale, duplicate or registry-only entries fail. Dependency versions
   remain independent. The build instructions now list the UI constant and
   owned Cargo lock entry with the other version authorities.

## Subsystem assessment

| Area | Evidence inspected | Release conclusion and remaining acceptance |
| --- | --- | --- |
| Desktop shell, setup and result presentation | Architecture/design rules, subsystem ownership, production frontend and playback records in the current candidate | TypeScript/build and focused UI checks are useful source evidence. Actual final native window, supported wide/narrow sizes, error/recovery, cancellation and saved-result replay remain required. Ongoing viewport changes require their own final-source checks. |
| Native host, worker and IPC | Thin-host boundaries, candidate worker verifier, release scripts and source-coherence inventory | Candidate record reports 15/15 benchmarks, 8/8 runtime comparisons and 558 coherent modules. Revalidate after any source/worker change and within the actual installer. An initial external-runtime comparison failed with unresolved cause; later successful replay does not explain it. |
| Import, geometry, project persistence and assembly | Ownership index, architecture and retained example/project checks | Preserve source identity, units, unsupported-object diagnostics and real/minimal importer fixtures. Full Python/parser suite and final native save/reopen are required; latest geometry inclusion is distinct from geometry accuracy. |
| DC PI, PEEC, PDN and network models | Solver status and numerical module ownership | Operational routes coexist with approximate/experimental models. Automatic convergence, large-scale performance and measured correlation remain method-specific gates; no broad production PI qualification follows from this release assessment. |
| SI, IBIS, sampled networks and calibration | SI08 validator implementation, native receipt chain, candidate limits | Validator regression tests pass; historical native evidence is stale against current runtime sources. Existing IBIS refinement and physical/device/protocol limitations remain. New transport/UI work must not promote sampled data to a qualified arbitrary network model. |
| Thermal, CFD, CHT and coupled physics | Latest solver integration, candidate and solver-status records | Native/runtime probes establish bounded execution. Proxy geometry, creeping-flow assumptions, failed detailed-CAD case and convergence limits remain explicit. No turbulence, arbitrary full-speed rotor or general assembly qualification is inferred. |
| Circuits, SPIKES, firmware, mechanics and propulsion | Architecture, solver status, subsystem index and platform scope | Independently versioned engines and trusted external-runtime paths retain their own admission. Experimental firmware/coupled propulsion work does not qualify real hardware or combustion; no new solver capability is enabled here. |
| External engines, acceleration, extensions and local assistant | Process/trust boundaries and source qualification inventory | Optional dependency discovery is distinct from validated execution. Preserve explicit trust, installation, resource, cancellation and unsupported-state gates. New process or security claims need their own review; this is not a comprehensive security audit. |
| Examples, Help, licensing and user documentation | Candidate catalog/Help evidence, LICENSE, LICENSING and THIRD_PARTY_NOTICES | Candidate records 38 examples, 76 text assets and Help checks. Keep example provenance, redistributability, prerequisites and model limits; audit actual final package notices and dependency bytes. Promotional images are not validation. |
| Delivery, provenance and publication | Version/identity/checksum guards, Windows input guard and Unix evidence | Version 0.4.2 is consistent including Cargo.lock. Freeze source, test artifacts, retain hashes/manifests and complete lifecycle acceptance. Publication remains canonical wayri only with its independent fail-closed guard. |

## SI08 evidence diagnosis

Inspected historical receipt:
[SI08-S05 native 20261024](parity/SI08-S05-native-20261024.json).
Both separately pinned validator files differ from current bytes:
`scripts/parity_multiport_native_gate.py` and
`tests/python/test_multiport_native_evidence.py`.

Of its 27 runtime/source paths, 13 no longer match the recorded identity:

- `scripts/verify_multiport_integration.py` and `scripts/verify_multiport_deembedding.py`;
- old `python/spike_core/sparameter_multiport_deembedding.py` and
  `python/spike_core/sparameter_sampling.py` paths are absent after ownership moves;
- `python/spike_core/service.py`, `service_simulation_handlers.py` and
  `service_sparameter_processing.py`;
- `tests/python/test_sparameter_multiport_deembedding.py`;
- `app/src/SParameterWorkbench.tsx`, `app/src/workerBridge.ts` and `app/package.json`;
- `examples/multiport_deembedding/run_fixture.py` and `docs/MULTIPORT_DEEMBEDDING.md`.

All nine original native artifacts still exist, as does the historical
integration receipt. Their existence does not bind them to current source.
The gate correctly rejects before accepting a stale native observation.
Changing only validator hashes would expose further mismatches, not resolve
provenance. Do not overwrite old snapshots, change completion assertions or
relax validation to obtain a green backlog.

Requalification should retain a fresh complete source snapshot, execute the
13 current numerical/contract/workflow integration tests plus actual desktop
handlers/buttons, and repeat native import/run/export, wide/narrow inspection,
editing invalidation, structured failure and recovery. Bind new artifacts and
validator versions; change the active backlog pointer only after the new gate
passes. Any alternative equivalence argument must explicitly review every
changed owner and preserve what was actually observed; it cannot be inferred
from path relocation alone.

## Checks executed for this assessment

Using repository `.venv/Scripts/python.exe`, Python 3.12.9:

| Command/check | Result |
| --- | --- |
| `-B -m unittest tests.python.test_release_automation tests.python.test_windows_msi_version tests.python.test_multiport_native_evidence -v` | 31 passed in 3.461 seconds; includes new Cargo.lock drift/admission checks, publication identity/package checks and synthetic native-evidence tamper controls. Synthetic artifacts do not count as new native GUI observation. |
| `-B scripts/check_architecture.py` | Passed importer, IPC, numerical, module-size, language, legacy-UI and documentation boundaries. |
| Direct `scripts.release_automation.version(Path.cwd())` | Passed, returned 0.4.2 with owned Cargo.lock checked. No network or publication action. |
| `-B scripts/check_solver_qualification_environment.py` | Passed dependency/native API inventory only: NumPy 2.4.2, SciPy 1.17.0, jsonschema 4.25.1, PyArrow 25.0.1, nanobind 2.11.0. Native extension SHA-256 `dfa8c3338442d1f7d92fb3a0d2667e7d261c410451e835e87ba3976c9e5785ce`. |
| `-B scripts/check_windows_release_inputs.py` | Failed against default local wheel directories as recorded above; no dependency or approval files were changed. |
| Read-only historical native receipt/source/artifact audit | Two validator mismatches, 13 runtime/source mismatches or missing paths; nine artifact paths exist. No receipts refreshed. |
| `-B scripts/check_documentation.py docs/BUILD_AND_RELEASE.md docs/validation/RELEASE_0_4_2_READINESS_20261026.md` and scoped `git diff --check` | Passed for the two edited documentation files and the scoped tracked changes. |

This assessment does not independently repeat the expensive full Python,
TypeScript build, Cargo or native solver campaigns coordinated by the
integration owner. Their final results must be recorded against the final
source snapshot, separately from these bounded checks.

## Final acceptance sequence

1. Finish coordinated edits, retain the complete candidate source and worker
   manifests, record compiler/runtime/dependency versions, and stop changing
   those inputs during acceptance. Preserve unrelated work.
2. Diagnose remaining failures and requalify SI08 as above. Keep prior failed
   logs. Run `python -m unittest discover -s tests/python -v`,
   `npm.cmd run check:architecture`, `npm.cmd exec tsc -- --noEmit`,
   `npm.cmd run test:parser`, and `cargo test` from their documented directories.
   Include affected frontend/worker/example/package suites and required C++
   kernel tests when those sources or bindings are included in the candidate.
3. Complete numerical method/source evidence and knowledgeable human release
   review. Explicitly hold incomplete capabilities and preserve their actual
   executable readiness and model status.
4. Build from the frozen inputs. Verify worker/resource membership and hashes,
   generated frontend embedding with no development server, exact internal
   installer version, actual dependency/license inputs, and installed behavior.
   Complete each claimed platform's clean/offline/upgrade/reinstall/uninstall
   and native UI/save/reopen acceptance. Do not reuse old-version receipts.
5. Review the concrete release artifacts, checksums, limitations and remaining
   platform scope with the owner, then use the publication/identity gates. A
   local development candidate remains useful before stable qualification;
   no stable designation should bypass these conditions.

Related current evidence: [candidate](RELEASE_042_CANDIDATE_20261026.md),
[solver status](../SOLVER_STATUS.md), and
[build/release instructions](../BUILD_AND_RELEASE.md).
