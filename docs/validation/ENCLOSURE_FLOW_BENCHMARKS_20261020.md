<!-- SPDX-License-Identifier: Apache-2.0 -->
# Refined enclosure and research-flow benchmark execution

20 October 2026. Synthetic mathematical verification only. No production,
measured enclosure, engineering turbulence or propeller qualification is claimed.
See the [workflow and remaining work](../ENCLOSURE_FLOW_RESEARCH.md).

## Current-source execution

All runs below used warnings as errors. The two prerequisite receipts bind
23 numerical/oracle/CLI/schema sources, interpreter, NumPy, SciPy and jsonschema
versions. Sources were unchanged across each execution. Any skip, expected
failure, unexpected success, assertion failure or source drift fails the runner.

| Actual run | Result | Elapsed seconds |
| --- | --- | ---: |
| Python 3.11.9 prerequisite suite | 50 passed, no skips | 85.153 |
| Python 3.12.9 prerequisite suite | 50 passed, no skips | 90.251 |
| Python 3.11.9 legacy CFD/CHT and actual worker regression | 129 passed, no skips | 26.672 |
| Public CHT v2 request/result benchmark, after private rotation extension | Passed all three case groups/four exact pairs | Not a performance qualification |

There are **179 distinct affected tests** in the Python 3.11 partition, not a
single full-project 179-test invocation. The additional Python 3.12 run covers
only the 50-test new numerical partition. Existing trusted native CHT/airflow
executables supplied the legacy integration checks; no new native build or
native numerical implementation is claimed.

Retained paths relative to the repository:

- `build/enclosure-prerequisites-20261020-py311-bound/receipt.json`, SHA-256
  `e11a1c643e126048aa7444af3d6934cd72feaa7ac5074c675ea3b45dbd599b7c`.
- `build/enclosure-prerequisites-20261020-py312-bound/receipt.json`, SHA-256
  `24f3611bbefb91f5ff8980b68e17333bcdda3260aaf62afa1371b5b76837138a`.
- Each prerequisite directory also retains its hashed `assertions.log`.
- `build/enclosure3d-legacy-postrotation-20261020.log` retains the separate
  129-test integration output.
- `build/enclosure-cht-v2-benchmark-20261020-postrotation/receipt.json`, SHA-256
  `1fab26b2fcd099e7201fe45acb6c5b709df55aed1f7af6a87da5de02e3461ba7`;
  exact requests/results and numerical observations are described in the
  [v2 record](ENCLOSURE_CHT_V2_VALIDATION_20261020.md).

Earlier un-suffixed prerequisite receipts are historical runs before the
runner added integration/schema/dependency binding; their hashes were not
patched. Reproduce the current runner with fresh output directories using the
[documented commands](../ENCLOSURE_FLOW_RESEARCH.md).

## What was checked

- Actual obstacle inertia and tensor-plane momentum refinement, independent
  re-entrant continuum forcing, disconnected gauges, strict representability,
  mass, work and heat checks, malformed requests and unsuccessful publication.
- Symmetric-stress cross-component coupling, positive strain work, exact
  constant-viscosity identity, independent variable-viscosity continuum cases
  and a deliberately incorrect scalar-diffusion negative control.
- Nonlinear positive-branch SA-noft2 transport, continuous polynomial source,
  substantial nonlinear/eddy-viscosity state, both modified-vorticity branches,
  homogeneous/zero limits, alternative starts and dimensional scaling.
- Actual rotating-frame momentum, exact rigid co-rotation pressure, work-free
  Coriolis coupling, independent three-component convergence, rotation sign,
  stable large-origin pressure recovery and zero-rotation equivalence.

Exact equations, units, reviewed primary sources, original derivations and
fixture observations remain in the separate [momentum](ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md),
[stress](ENCLOSURE_SYMMETRIC_STRESS_20261020.md),
[SA](ENCLOSURE_SA_TRANSPORT_20261020.md) and
[rotation](ENCLOSURE_ROTATING_FRAME_20261020.md) method ledgers.

The coarse quadratic-viscosity 4/8/12 probe remains **unqualified**: its first
order was 1.76826, below the unchanged >1.8 gate. An additional 8/12/16 study
passed the same gate; that does not erase the failed coarse interval. The
re-entrant obstacle finest error remains about 10.4%, not a general 2% bound.
Passing this bounded assertion suite therefore does not mean every exploratory
case or original full-suite release gate passed.

## Other checks and limits

Source compilation and scoped whitespace checks passed. The architecture check
initially failed on an unrelated `fieldVolumeModel.ts` array-extrema guard;
after that concurrent owner's change it passed on the current tree. No UI file
was edited by this increment. The reference inventory is regenerated separately.

Linux/MPI, clean-machine packaging, full-project/UI tests, hardware correlation,
confined octree momentum AMR, transient momentum, joint RANS residuals,
engineering wall-layer qualification, turbulent heat closure, rotating blades,
rotor/stator or ALE interfaces and propeller loads remain outside these passed
checks. Existing public flags for turbulence and rotating machinery stay false.
Knowledgeable human numerical review is still required before release.
