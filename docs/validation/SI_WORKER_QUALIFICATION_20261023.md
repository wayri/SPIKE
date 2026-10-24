<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI worker rebuild and qualification attempt — 23 October 2026

## Requested outcomes

| Outcome | Evidence-backed state |
|---|---|
| Coherent Windows worker rebuild | R3 completed under the coordinated hold, passed final active-source/payload checks and retains its matching inspected source/schema baseline |
| Vendor AMI interoperability | Blocked at binary/terms admission; no external model executed |
| Marble/WREN SERDES and 10GbE qualification | Not achieved: actual high-speed pair extraction rejects the retained geometry; physical/protocol evidence remains missing |

Neither passing source tests nor an installer build would change the last two
states. This record does not claim complete release or physical qualification.

## Coherent Windows worker

Final artifact:
`build/si-qualification-worker-r3-20261023/resources/spike-worker/spike-worker.exe`

- Windows x64, source version `0.4.0-alpha.1`, Python 3.12.9/PyInstaller 6.21.0.
- 19,382,897 bytes; SHA-256
  `75397e6cfcff1980a581c66673ea86d849a36f2ffa6e6faa9331a2b5c01ec828`.
- Adjacent v2 manifest: 1,474 payload files; permanent benchmark probes 15/15,
  zero failures/skips; source/frozen runtime comparisons 8/8.
- All **499 inspected frozen source modules** match current compiled source,
  including required EM/co-simulation modules. This scope is Python code, not
  a claim of native C++ source-to-binary equivalence.
- All **262 schema JSON files** match source. Schema manifest SHA-256:
  `66722db519f375e979ee4c486dbca6c052469c6f93f5a635301198e8b653b043`.
- The existing packaged-payload verifier passed all five integrity checks:
  `build/si-qualification-worker-integrity-r3-20261023.json`.

The build now enforces `verify_packaged_source_modules` after its execution
probes and rechecks schemas before writing a successful manifest. Changed
constants, nested code, line tables, absent source, empty inspection scope and
missing required modules fail closed; filename relocation alone is normalized.
This closes the earlier process gap where runtime snapshots could agree while
unexercised frozen code was stale. No numerical tolerances were changed.

Final active-source comparison:
`build/si-qualification-worker-source-handoff-r3-20261023.json`.
Build log: `build/si-qualification-worker-r3-20261023.log`.
The old candidate and its failed later comparison are retained as historical
evidence, not overwritten or silently promoted.

Later handoff check `build/si-qualification-worker-source-handoff-20261023.json`
correctly rejects a subsequent `assistant_harness` edit. R2 then built and
passed its eleven analytical process requests (executable SHA-256
`756a4aac5dc4385c9c22ba1b5794e3243399c9708782b7d876cac438f5336498`),
but its mandatory build guard rejected a concurrent `cfd_tetra_mesh` edit.
No successful R2 worker manifest or source snapshot was published. Its log and
passing-but-insufficient numerical report remain retained, not promoted. The
owner authorized coordination of a maximum ten-minute backend freeze across
the five active SPIKE chats; no shared source was reverted to force a pass.

R3 completed its mandatory gates at 13:23:03 UTC. The final active-source and
payload checks passed before the earliest hold deadline of 13:23:53 UTC
(18:53:53 IST). Four backend-scope holds were confirmed; the remaining chat
was doing UI/help work and did not supply an explicit acknowledgment. Source
guards, not presumed acknowledgments, establish the observed coherence.
The hold expired at its agreed deadline without an extension; release-message
tool calls finished at 13:24:06 UTC. Other chats may resume edits, which are
not part of this retained candidate.

Matching source/schema baseline:
`build/si-qualification-worker-r3-20261023/inspected-source-baseline`.
Its `SOURCE_SNAPSHOT.json` SHA-256 is
`4ecea222cac1c3061ad74fe6006af18e6175a2ae386c468ea0e4de3a054c565e`.
The source guard also passes explicitly against that retained baseline:
`build/si-qualification-retained-baseline-check-20261023.json`. It is not a
certificate for later working-tree changes or a complete rebuildable/native
release-source archive.

Rebuild into another fresh directory, then replay the source guard and
analytical process reference:

```powershell
.venv/Scripts/python.exe scripts/build_packaged_worker.py --candidate-root build/si-qualification-worker-new
.venv/Scripts/python.exe scripts/verify_packaged_source_modules.py build/si-qualification-worker-new/resources/spike-worker/spike-worker.exe --require-em-cosimulation --output build/worker-source-new.json
.venv/Scripts/python.exe scripts/verify_serdes_worker_reference.py build/si-qualification-worker-new/resources/spike-worker/spike-worker.exe --output build/serdes-process-new.json
```

Current-source comparisons are point-in-time checks. Subsequent source edits
require a new comparison/rebuild; this artifact does not freeze the shared
working tree or qualify unexecuted later features.

`scripts/capture_worker_source_snapshot.py` retains matching Python/schema
bytes under a fresh build directory after comparing them to the actual frozen
code and bundled schemas. Its SHA-256 catalog preserves that inspected baseline
when other chats edit the working tree. It rejects source/schema drift before
publishing, requires the EM owners and bounds per-file/aggregate source data.
This is not a complete release-source archive, native equivalence check or
permission to call a snapshot comparison a latest-working-tree comparison.
The source checker can explicitly use `--source-root <retained-baseline>`;
its report names the baseline. The builder's default check still uses the
active repository and is not relaxed by this option.

## Actual frozen 10.3125 GBd analytical replay

`scripts/qualify_serdes_reference.py` now accepts an explicit workflow adapter.
The new `scripts/verify_serdes_worker_reference.py` executes the same eleven
requests through fresh frozen-worker processes. Stimuli, seven criteria and
tolerances are unchanged. Errors, failed criteria, missing executions or
executable replacement invalidate the run. The executable hash is bound before
and after; dependency-file integrity is checked separately through the manifest.

Final report: `build/si-serdes-frozen-reference-r3-20261023.json`.
It records eleven actual frozen-process requests bound to the final R3 hash.

| Existing criterion | Actual frozen result | Unchanged gate |
|---|---:|---:|
| Represented rate | 10,312,500,000 Hz | absolute error at most 0.01 Hz |
| Loaded attenuator gain/phase maximum complex error | 1.1443916996305594e-16 | 2e-12 |
| Shunt-RC transfer maximum complex error | 1.2434497875801753e-14 | 2e-12 |
| Matched one-UI delayed eye | 0.3999999999999995 V | 0.4 V within 1e-10 V |
| 8/16 samples-per-UI sensitivity | 0.0012593823285529382 V | at most 0.01 V |
| Fixed-band final successive refinement change | 7.139265766176184e-6 V | at most 2e-4 V, preserving the rate |
| Insufficient bandwidth | Rejected | must remain blocked |

The [reference formulation](../SERDES_REFERENCE_QUALIFICATION.md) documents the
independently authored gain/delay and RC oracles, reference sources, units and
limits. This increment adds a process adapter, not new governing mathematics.
The refinement change is an engineering repeatability gate, not an error bound.
These synthetic cases are not Marble/WREN channels, measurements, a qualified
CDR/BER receiver or an Ethernet compliance procedure. `production_qualified`
remains false and compliance remains not evaluated. Orchestrator runtime
metadata is distinct from the bundled-runtime identity in the worker manifest.

## Actual board pairs, not substitute clock paths

The [board-pair evidence](SI_BOARD_PROTOCOL_READINESS_20261023.md) identifies
real FPGA/switch and connector pads. Both complete native imports retain their
original source hashes and geometry. The explicit nominal conductivity
scenario remains an assumption, not measured foil data. Dielectric and source
records are not invented or altered.

The executed both-mode report is
`build/si-board-protocol-readiness-both-modes-20261023.json`, SHA-256
`3b18963b76e34e6a853db0bca565af49c75315c024cf4f25d67e1e575c092d11`.
All nine bound implementation hashes were rechecked against current source.
There were **36 real extractor calls**: 18 differential pairs, each in strict
and declared piecewise-planar mode. All rejected. In piecewise mode, 11 pairs
contain unsupported vias and seven have unequal P/N segment counts. The latter
reject before separation/skew tolerances are evaluated; increasing those
tolerances would not repair that failure. Reference/dielectric gates were not
reached, so this does not assert they would pass next.

Actual 10GbE completion requires reviewed general path/transition extraction,
return and package/connector/switch networks, an exact operating configuration,
applicable reference planes/fixtures, Tx/Rx models and independently correlated
normative comparisons. The earlier admitted single-clock paths do not supply
those missing networks. Public SFF documents were reviewed for applicability,
not treated as permission to call arbitrary FPGA SERDES a compliant link.

## Vendor-model admission

The [public admission audit](AMI_PUBLIC_ADMISSION_20261023.md) retains exact
archive/member hashes and primary-source links. The official legacy kits are
PE32, not the host's AMD64 target. The inspected TI x64 download is an unsigned
installer; installed static readers could not expose its inner Windows models,
matching parameter definitions or exact terms. Other candidates require
account/consent workflows or offer source rather than reviewed binaries.

No installer or external native model was executed. Public downloadability was
not equated with trust, accepted rights, supported parameters or dependencies.
The owner selected preparation of an [isolated-VM evaluation
plan](../SI_AMI_ISOLATED_VM_EVALUATION_PLAN.md). The plan is now provided;
no VM/installer/model was executed or agreement accepted. Execution still
requires the named environment and staged approval decisions. This does not
change the host's current-user-access trust boundary.
Even a future admitted TI interoperability run would not model the boards'
different FPGA devices or close their physical link qualification.

## Tests and remaining release gates

- `build/si-qualification-integrated-tests-20261023.log`: **130 passed**, zero
  skips, covering current SI/AMI/PAM3/material paths, packaging guards and
  source/adapter analytical SERDES checks.
- `build/si-qualification-board-tests-20261023.log`: **9 passed**, zero skips,
  including real-extractor positive/negative authored fixtures, immutability,
  source identity and rejected physical geometry.
- A concurrent earlier `service.py` change required nine genuine parity
  replays: **123 passed**, zero skips. The `si-qualification-r4-20261023`
  receipts preserve earlier evidence. All 50 completed stages validate with
  no drift; `build/si-qualification-parity-20261023.log` records the result.
- Focused packaging tests include rejection of stale frozen code. These are
  not a fresh whole-repository test-suite pass.
- Source-snapshot regression tests: **5 passed**, zero skips, in
  `build/si-worker-snapshot-final-tests-20261023.log`. Independent review found
  schema-mutation and escaping-build-root risks; both were repaired with
  rejection tests before the final snapshot was captured.
- Final integrated guard/analytical/board subset after those repairs: **29
  passed**, zero skips, in `build/si-qualification-final-guard-tests-20261023.log`.

RF-network guidance strengthened explicit physical identity, applicability and
independent checks; desktop-release guidance kept source, frozen runtime and
installation evidence distinct. No gate was waived. The earlier desktop
installers were not replaced. Linux, clean-machine/offline/upgrade/uninstall,
full-suite, independent/measured physical correlation and knowledgeable human
numerical/security release review remain separate, unclosed requirements.
