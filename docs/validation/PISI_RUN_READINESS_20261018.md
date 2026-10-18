<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI/PI executable workflow readiness: 18 October 2026

**Passed for the bounded source-checkout workflows below.** This record
establishes runnable SI/PI with explicit models and admission, not arbitrary
board extraction, native visual acceptance or physical/production qualification.
Use [Run SI and PI now](../RUN_SI_PI_NOW.md) for actual task instructions.

## Changes that enable execution

- Added `pdn-network request.json` to the existing CLI-to-worker path. It runs
  `evaluate_pdn_network`, retaining the underlying result, model status, error
  handling and finite-JSON output. No numerical solver was changed.
- Fixed the SI workbench's default four-port to two-port channel transition.
  Previously it retained zero-based receiver port 2, and the actual backend
  rejected it with `Port must be an integer in 0..1.` The frontend now remaps
  only a simple default through path, preserves endpoint model parameters and
  shows a port-review notice. Custom source/receiver/passive/edit mappings
  remain intact and block incompatible Run with actionable messages.
- Added original supplied RC/RLC PI setup files and a real-subprocess readiness
  runner. The RLC model includes source R/L, two decap ESR/ESL branches and a
  finite-rise load pulse. Component values are assumptions, not extracted or
  vendor-qualified parameters.

## Actual end-to-end execution

```powershell
.venv/Scripts/python.exe scripts/check_pisi_readiness.py --native-python build/qualification-py311/Scripts/python.exe --output-dir build/pisi-readiness-20261018-verified
```

All **nine cases passed**. The report
`build/pisi-readiness-20261018-verified/readiness.json` retains each command,
exit status, input copies/hashes, output hashes, model status and metrics.
Raw result JSON and CLI logs are retained beside it. Original solver source
files and runner hashes are included; this is executed evidence, not a fixture
copy or mock worker.

| Case | Executed acceptance | Observed result |
| --- | --- | --- |
| Explicit RC PI | AC response and finite-rise transient against independent closed forms | Maximum requested droop 49.997487 mV |
| Explicit RLC PI | Parallel-branch complex impedance reference and transient energy balance | Maximum requested droop 23.440927 mV; relative energy residual 1.03e-13 |
| RLC timestep refinement | 0.5 ns versus 0.25 ns at identical observations, unchanged budget 1 uV + 0.2% of refined voltage | Maximum observation difference 3.120482 uV |
| Coupled SI | Actual four-port frequency, finite receiver waveform/eye and TDR | All requested stages completed; open finite reference eye |
| 10G numerical SI reference | Actual loaded frequency, receiver waveform/eye and TDR | All requested stages completed; no protocol-compliance claim |
| Touchstone reinspection | Reimport the SI-exported unloaded channel | Four-port file completed reinspection |
| Routed-copper DC PI | Uniform-conductor R=length/(sigma*width*thickness) at 1 A | Load drop 4.926108 mV, approximate model |
| Routed-copper AC PI | Actual native R/L driving-point sweep | Completed/approximate; distributed C disabled and SI uses remain blocked |
| Routed-copper transient PI | Actual finite-rise load, 8 ns step at recommendation | Maximum internal reported drop 12.049437 mV, approximate model |

For the RC oracle, KCL gives Z=1/(1/R+j*omega*C), and a unit current ramp gives
tau*y'+y=R*min(t/rise,1), tau=R*C. Its rising solution is
y=R*[t/rise+(tau/rise)*expm1(-t/tau)], followed by exact exponential relaxation
toward R. The RLC frequency oracle independently combines source
R+j*omega*L and two ESR+j*(omega*ESL-1/(omega*C)) branches in parallel.
These are original elementary circuit references for workflow verification;
no production mathematics was added or changed. The existing
[PDN model limits](../PDN_SCREENING.md) and [SI method limits](../SI_WORKFLOW.md)
remain in force.

The RLC example's initial 2 ns versus 1 ns comparison did not meet the frozen
observation tolerance. Refining the original 10 us window hit the existing
20,000-step admission limit. The final example uses a declared 4 us pulse/ringing
window and 0.5/0.25 ns timesteps; it passes the original tolerance and resource
limit. Stored energy may remain at the end. No tolerance or step budget was
relaxed, and no settled-state or intersample-peak convergence is claimed.
The initial failed runs remain in `build/pisi-readiness-20261018/` and
`build/pisi-readiness-20261018-refined/`.

## SI frontend-to-backend handoff

`build/pisi-si-frontend-handoff-probe.py` executes the actual compiled frontend
assignment helper and passes its mapped setup into the canonical synthetic
geometry fixture and real SI backend. **One case, ten assertions passed**, with
1,025 frequencies, zero-based source 0 and receiver 1. The two-port network,
time-domain and TDR stages completed. Result and helper SHA-256 identities are
retained in `build/pisi-si-frontend-handoff-summary.json`; actual result is
`build/pisi-si-frontend-handoff-result.json`. Reproduce:

```powershell
.venv/Scripts/python.exe build/pisi-si-frontend-handoff-probe.py
```

This is a synthetic canonical path, not a user board or native GUI screenshot.

## Regression and architecture evidence

- **69 Python CLI/PDN/SI tests passed**, zero skips/failures/errors. This includes
  the actual new CLI subprocess, independent RC frequency/ramp assertions and
  invalid-model nonzero exit. Log: `build/pisi-ready-regressions.log`.
- `npm run test:si-workflow` passed actual component/helper tests for default
  geometry/Touchstone transitions, parameter preservation, custom mapping
  retention/blocking, duplicate/invalid assignment recovery and worker payload.
  Log: `build/pisi-ready-si-ui.log`.
- SI plot tests and shared button/control standards passed:
  `build/pisi-ready-si-plots.log`, `build/pisi-ready-buttons.log`.
- Full frontend `npm run build` passed TypeScript and Vite. The existing large
  bundle/chunk warning remains; no threshold was changed. Log:
  `build/pisi-ready-frontend-build.log`.
- Architecture passed: `build/pisi-ready-architecture.log`.

Native visual interaction and installed-package acceptance were not tested.
No full repository/release test success is claimed by these focused checks.

## What remains necessary for a user board

No user board/project, target rail/link, terminals, constraints or model files
were provided during this check. Its geometry, connectivity/return, materials,
source/receiver/VRM models, frequency/time resolution and extraction validity
must be admitted separately. The geometry SI path has bounded planar-path and
reference coverage; arbitrary vias, branches, launches and return transitions
remain unqualified. Whole-board PI and SI cannot be called signoff-ready from
these reference runs. Verified supplied/external networks and explicit lumped
PI models are usable now within their declared scope.
