<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Cambridge measured SI fixture admission

The native network pipeline now has an executable measured-data example, distinct
from analytical/synthetic validation. The source is Schaich, Molnar, Al Rawi and
Payne, [Experimental Data supporting “Surface Wave Transmission Line Theory for
Single and Many Wire Systems”](https://doi.org/10.17863/CAM.65674), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The dataset license is
not changed by this repository's source-code license.

The four original `Two_Wire_S31/S32/S41/S42.S2P` files contain HP8722D VNA
measurements, 1601 frequencies from 50 MHz to 15 GHz, with 50-ohm references.
The approximate fixture is a pair of 50-cm bare copper wires, diameter 0.5 mm,
separated by about 1 cm, with planar surface-wave launchers. It is not a PCB.

## Physical port interpretation

The repository metadata supplies this physical layout:

```text
4 ---------------- 2
3 ---------------- 1
```

Each file is a two-port measurement; its local S21 is the transfer between the
physical pair named by the filename. The other physical terminals were terminated
in 50 ohms. S41 therefore supplies physical 1-to-4 far-end cross-wire coupling.
Physical pairs 1-to-2 and 3-to-4 are absent. NEXT, a complete four-port matrix and
arbitrary four-port retermination cannot be recovered from these files. Missing
entries are never replaced with zero or inferred from symmetry.

## Reproduce

Run from the repository root, choosing a new output directory for each run:

```powershell
python scripts/admit_cambridge_measured_si.py --download --output build/cambridge-measured-si-new
python scripts/admit_cambridge_measured_si.py --input build/cambridge-measured-si-new/data --output build/cambridge-measured-si-replay
python scripts/benchmark_cambridge_measured_si.py --input build/cambridge-measured-si-new/data --output build/cambridge-measured-si-new/benchmark.json
node app/scripts/export-si-crosstalk-results.mjs --input build/cambridge-measured-si-new/measured-channel-result.json --output build/cambridge-measured-si-new/ui-export
python -W error -m unittest tests.python.test_cambridge_measured_si_admission -q
```

Admission checks the upstream published MD5 and byte count and records a local
SHA-256 for each original file. MD5 is a repository integrity cross-check, not
strong authentication. Offline replay checks the admitted SHA-256 as well.
Repository metadata, original bytes and attribution remain beside the analyses.
The exported HTML embeds attribution and a license link, and has an attribution
sidecar. No source data conditioning or fabricated measurement samples are used.

## Executed evidence and limits

`build/cambridge-measured-si-20260907` contains actual admission and analysis;
`ui-export-attributed` contains the attributed HTML/CSV views. The separate
`build/cambridge-measured-si-offline-20260907` run verified offline replay.
Five measured processing runs after one warmup had median 0.246264 seconds on
the recorded local machine, with identical analysis digests across all six runs.
Measured physical 1-to-4 peak transfer is -7.3188 dB at 264.90625 MHz, including
the fixture launchers. This is a measured response, not a prediction error.

Exact launcher geometry, quantitative calibration/measurement uncertainty and
qualified dimensional tolerances are not available in this admitted metadata.
Consequently this validates measured-file admission and network postprocessing,
**not** geometric field-solver correlation, PCB accuracy or production readiness.
The output retains those qualification flags as false.
