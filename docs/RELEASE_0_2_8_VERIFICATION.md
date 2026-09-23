# SPIKE desktop 0.2.8 verification

Date: 2026-09-05. Status: **built, not installed**. Unsigned engineering preview;
no physics or production qualification is promoted.

## Delivered in this candidate

PI voltage sources, current sinks, independent-batch terminals and explicit
returns use grouped single-row tables. Pad selection and waveform details open
for one row at a time. SI sources/aggressors and receivers also use endpoint
tables, retaining port, model and IBIS controls. PI/SPICE edits mark the project
dirty. The reviewed owned-SPIKES structured-workspace route is selectable.

The installed 0.2.7 does not contain these tables. Installation and native visual
acceptance remain pending: Windows was locked while SPIKE was open. No forced
termination or silent discard of project edits was attempted.

## Verification and source boundary

- 45 frontend regression scripts plus TypeScript: 46/46 pass, including actual
  rendered PI/SI table and edit-handler checks.
- Production frontend build, 29 Rust tests, 12 error tests and 13 schema tests
  pass; the worker was rebuilt, not reused. Build-time runtime/native gates pass.
- Final source Python suite: 1,409 tests, zero failures/errors, one skip. Three
  earlier visual-bundle fixture failures were corrected to expect the intentional
  `include_layout_layers=True` contract; no security gate was weakened.
- A post-build checkpoint compares all 177 frozen Python modules with source:
  all match. Subsequent parallel edits changed `python.spike_core.models` and
  `python.spikes.netlist`; these are **not in this candidate** and are retained
  for a later build. The final source-suite result must not be described as an
  immutable exact-binary full-suite qualification. Both checkpoint and drift
  reports are retained.
- Exact installed-image checks and interactive table acceptance are pending.

Evidence is archived under
`artifacts/windows/releases/0.2.8-tabular-inputs-20260905/`, including installer
and worker manifests, runtime report, source snapshots and test logs. Historical
0.2.6 and 0.2.7 archives are unchanged.

## SHA-256

| Artifact | SHA-256 |
|---|---|
| SPIKE_0.2.8_x64-setup.exe | `01510ea97244a48ad7b30b3edaa82d257c7c2fde0edc347d9e40c6cefdb40de3` |
| SPIKE_0.2.8_x64_en-US.msi | `048a9ec884ab68ec8418f9b5a9d5540ea66bb5f11c0d05d43f6c864600e8fff3` |
| spike-desktop.exe | `c15206ada413beafd0ce240e7c69436df26fcea0e67e474cb19cc132af3e346e` |
| spike-worker.exe | `a5159ea60f54bc107b1295b924cd1e849dd82f642397677ff079cb65c19f1961` |

After unlock: save and close SPIKE normally, install this exact candidate, verify
installed hashes/version, run packaged-worker acceptance, and inspect PI/SI
tables in the installed app. Installation alone is not workflow or signoff evidence.
