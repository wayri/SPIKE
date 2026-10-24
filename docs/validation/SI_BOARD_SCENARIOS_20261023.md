# SI board material and reference scenarios — 23 October 2026

Subsequent evidence: [the coherent worker rebuild and actual SERDES pair
attempt](SI_WORKER_QUALIFICATION_20261023.md) supersedes this record's final
worker-coherence failure for its newly identified artifact. It does not erase
the older failed comparison or promote clock diagnostics to board compliance.

## Outcome and scope

The bounded SI path now accepts an explicitly prepared, revision-bound scalar
conductivity scenario and an exact retained reference-zone selection. This
does not infer copper properties, reconstruct missing plane geometry, merge
return regions or qualify a physical PCB. Existing geometry, resource and
numerical gates remain in force.

The [material workflow](../SI_MATERIAL_SCENARIOS.md) documents the request,
immutable result and transport bounds. Both uniform and coupled extraction
bind the physical material inputs and declared scenario context into their
geometry/result identity. An omitted competing reference region remains an
explicit approximation. Unknown IDs, holes, absent outlines and incomplete
coverage still fail rather than becoming ideal reference planes.

## Original derivation and independent checks

This increment changes preparation, identity and selection, not the governing
quasi-TEM model. The independent DC check recomputes selected track length from
retained endpoints in millimetres, converts to metres and evaluates
`R = length / (conductivity * width * thickness)` in ohms. At DC the existing
lossy line reduces to a series resistance. With equal real 50 ohm references,
its forward power-wave transmission is `S21 = 100 / (100 + R)`. The verifier
compares actual complex network entries to this independently constructed
oracle with an absolute tolerance of 1e-12. Reciprocity uses maximum absolute
`Sij-Sji` at 1e-10; sampled passivity uses an independent full SVD with maximum
singular value at most `1+1e-10`. These checks do not establish broadband
causality, return-current completeness, mesh convergence or measured accuracy.

Reviewed nominal-property basis: NBS Handbook 100, *Copper Wire Tables* (1966),
Part I section 1.1(a), printed page 2, defines the historical IACS conductivity
at 20 degrees Celsius; the current [NPL conductivity service](https://www.npl.co.uk/products-services/magnetics/ac-and-dc-conductivity)
also identifies 58 MS/m with 100% IACS and distinguishes bulk DC and surface AC
conductivity. [The primary handbook](https://nvlpubs.nist.gov/nistpubs/Legacy/hb/nbshandbook100.pdf)
is a nominal reference, not a measurement of the boards' foil. We deliberately
use an explicit **assumed** 58,000,000 S/m at 293.15 K scenario, without a
temperature law or frequency/roughness calibration. These established checks,
code and fixtures were independently authored; no third-party solver or model
implementation was examined or adapted.

## Executed Marble and legacy White Rabbit diagnostics

Reproduction uses `scripts/verify_si_real_boards.py` and the command in the
material workflow, with a fresh output filename. The current retained report
is `build/si-real-board-scenario-final-20261023.json`; it records source hashes,
exact requests, geometry, material provenance and numerical results.

Marble v1.4.4 native KiCad source SHA-256:
`3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.
Its complete import contains 37,380 tracks, 5,272 pads, 3,664 vias and 124 zones.
The selected `/WhiteRabbit/SI570_CLK_N` path over GND/In1.Cu admits only in
`piecewise_planar` mode; the strict straight-path gate still rejects bends.
The eight retained segments total 7.116085022555 mm at 0.13 mm width and
35 micrometres thickness. Under the declared nominal scenario:

| Check | Executed value |
|---|---:|
| Independent DC trace resistance | 0.026965081555721852 ohm |
| DC S21 absolute error | 1.1102230246251565e-16 |
| Maximum reciprocity error | 4.441197019893352e-16 |
| Maximum sampled singular value | 0.9999999999999999 |
| Network | 2 ports, 65 samples, DC–64 MHz, 50 ohm |

Those frequency/reference choices are diagnostic inputs, not actual board
operating conditions or 10GbE limits. Bend/discontinuity, quasi-TEM, loss-model
and unrepresented return-current limitations remain in the result.

The legacy converted White Rabbit core source SHA-256 is
`6ae6d75d44c89200ec358ad9f43403ff6b8bea4a3580758f160588fa91502aff`.
Its GND/In1.Cu candidates are intent records with no retained physical outlines.
Explicitly selecting `b4ae1c1d-464f-5047-a0fd-ca183b7f23b8` therefore still
rejects polygon admission. No retained material has the exact copper class,
so the copper-only scenario also rejects rather than relabeling it. Conversion
losslessness is unverified. The combined report returns nonzero overall;
Marble's admission is not an all-board success or a repair of this conversion.

## Separate native CERN WREN-Ie diagnostic

To avoid conflating conversion defects with native-board admission, a separate
native KiCad [WREN hardware](https://gitlab.cern.ch/be-cem-edl/chronos/wren/wren-hw)
fixture was obtained at commit `816b7598a89151a8250fa5fa945d2a0154669325`, path
`hw/EDA-04968-V2-0/EDA-04968-V2-0.kicad_pcb`. Source SHA-256:
`f98009ba98a0f7b302fe7c0f48fa64016a856af7d3989d3f6b7082435f9b2b9b`.
The hardware is identified by the [WREN project](https://gitlab.com/ohwr/project/wren/-/wikis/White-Rabbit-Event-Node)
as CERN-OHL-W-2.0+. The official license text at cernohl commit
`550e7d4f3e9f4288c7e04b05384c53e1fac44aa0` has SHA-256
`b40b92b17f7d579da2a317725ca02141672aaea7dd94f80ca78a86c5acb13b1b`.
Source board and notices remain in ignored local evaluation storage; they are
not an added redistributed example or installer payload. Upstream solver code
was not consulted. This is not the legacy White Rabbit switch fixture.

The complete native import reports `completed_with_warnings`: 10,201 tracks,
1,418 arcs, 3,542 pads, 2,318 vias, 172 zones and 973 nets; zero reported
unsupported objects and geometry errors. This records importer diagnostics,
not independent import-losslessness certification. The retained compact design
is about 48.8 MB and uses the in-process preparation API, not oversized IPC.

Reproduce after obtaining that exact licensed board at the pinned local path:

```powershell
.venv/Scripts/python.exe scripts/verify_wren_si_scenario.py --signal-net /clocks/WR_CLKOUT_C_P --output build/wren-clkout-c-p-new.json
```

The verifier pins the source before importing and records its own and relevant
core/importer source hashes. Exact GND/In1.Cu filled-zone ID
`ea044049-5fb5-596f-b5a6-61bcdbf83727` passes projected-footprint coverage for
seven F.Cu tracks on `/clocks/WR_CLKOUT_C_P`. The piecewise path is
11.989780982052127 mm long, 0.115 mm wide and 35 micrometres thick, with
0.145 mm spacing. Six retained 45-degree bends remain outside the local
discontinuity model; strict straight-path admission still rejects them.
The same explicit nominal conductivity scenario and diagnostic DC–64 MHz,
50 ohm sweep give:

| Independent check | Executed value |
|---|---:|
| DC trace resistance | 0.05135909608932159 ohm |
| DC S21 absolute error | 0 |
| Maximum reciprocity error | 3.332294980281256e-16 |
| Maximum sampled singular value | 0.9999999999999998 |

Current evidence is
`build/wren-si-fixture-20261023/wren-clkout-c-p-admission.json` (23,521 bytes),
SHA-256 `52e1cbd7d41cc803090202bbdf2a457a91e4a0df2fa4dc45caac2b0a18aaf947`.
All seven recorded implementation-source hashes were rechecked against current
source. A separate `/WR_CLK.ABSCAL` attempt failed reference coverage; the
verifier did not simplify geometry to admit it. These results verify execution
and bounded network invariants, not measured channel accuracy, complete board
returns, pair extraction, 10GbE operation or compliance.

## Verification and Windows frozen worker

- `build/si-board-scenario-integrated-regression-20261023.log`: **109 passed,
  zero skips**, including material admission/schema/worker, explicit reference
  selection, unchanged existing channel/protocol tests, native AMI, PAM3 and
  the four WREN verifier cases. This supersedes the earlier 105-test run.
  Rejected geometry propagation, pinned source/scenario binding and
  no-overwrite output are tested, not just the successful path.
- Nine affected completed parity stages were genuinely replayed against their
  unchanged assertions (122 tests in the final stage set, zero skips).
  `SI01-S01` was replayed once more after context binding (22 passed).
  The receipts end in `si-board-scenario-20261023`, with the current SI01-S01
  receipt at that point ending in `si-board-scenario-r2-20261023`.
- Concurrent shared `service.py` drift subsequently invalidated nine stages:
  GP07-S01, SI01-S01 and SI02-S07 through SI02-S13. All nine were genuinely
  replayed again with unchanged assertions: **123 passed, zero skipped**.
  Current receipts end in `si-board-scenario-r3-20261023`; earlier evidence is
  retained. The final completed-stage audit has no remaining drift and the
  backlog validator passes. The post-parity release gate remains closed.
- The isolated Windows x64 worker is
  `build/si-board-scenario-candidate-20261023/resources/spike-worker/spike-worker.exe`:
  19,349,114 bytes; SHA-256
  `a8ed77e3f6b70138c977c7aca36bd16d8f9596e8189635fa035543f4e9de8a90`.
  Its adjacent v2 integrity manifest records Python 3.12.9/PyInstaller 6.21.0,
  15/15 benchmark probes and 8/8 source/frozen runtime comparisons.
- The actual frozen-process material/reference probe passed immutable
  preparation, explicit plane selection, ohmic resistance and material identity
  checks. Its PAM3 identity/two-eye and rare-tail probes also passed.
- `build/si-board-scenario-source-match-20261023.json` matched all **494**
  checked source modules immediately after the build. All **262** packaged
  schema JSON files, including the manifest, matched source bytes.
- A later final check, `build/si-board-scenario-source-match-final-20261023.json`,
  correctly **fails** current whole-tree coherence: concurrent changes in
  `python.spike_core.service` and `python.spike_core.service_propulsion_pod`
  are newer than the worker. No other checked module differs. The candidate's
  executed probes remain evidence for that artifact, not a current-source
  installer or a reason to bypass the mismatch gate. A new coordinated build
  is required before release.
- After detecting that source drift, the actual source-worker material and
  PAM3 process tests were rerun: **6 passed**, zero skips, in
  `build/si-board-scenario-service-recheck-20261023.log`. This confirms those
  current dispatch paths, not the unrelated new propulsion feature or complete
  frozen-source coherence.
- Architecture, generated reference-inventory coherence and scoped whitespace
  checks passed after integration. The inventory records references; it does
  not imply implementation adoption or qualification.

RF-network skill guidance motivated explicit reference/provenance handling and
independent network checks. Desktop-release guidance kept source, frozen worker
and installer evidence separate. Neither is a physical qualification shortcut.

## Remaining gates

No fresh whole-repository suite, desktop installer installation, interactive
visual acceptance, Linux packaging or clean-machine/offline/upgrade/uninstall
qualification is claimed here. Earlier installers do not contain this increment.
The separate native AMI host remains trusted-development-only, not an untrusted
code sandbox or generally qualified vendor loader. Board-level Tx/channel/Rx,
generation-specific limits, physical return-path closure, vendor interoperability,
independent/measured correlation and knowledgeable human release review remain
open. No gate or unsupported state was removed to obtain these results.
