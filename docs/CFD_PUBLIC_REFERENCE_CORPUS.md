<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Public experimental CFD reference corpus

Selection date: 2026-09-07. These are primary sources with identifiable
experimental methods, geometry and/or error information. Recency and citation
counts alone do not establish a useful validation dataset. No third-party
solver implementation was copied into SPIKE.

## Admitted measured reference

[NASA TMR Driver–Seegmiller backward-facing step](https://tmbwg.github.io/turbmodels/backstep_val.html)
provides experimental wall skin friction, pressure and velocity profiles.
The selected straight-opposite-wall case uses Re_H approximately 36,000;
the site documents an earlier incorrect 50,000 label. Its Cf normalization
uses upstream reference conditions, not an arbitrary inlet speed.

Downloaded original `cf.exp.dat`: 20 measured stations, including published
error values. SHA-256:
`cd9b6434b7956bc58e859de6af654cd7f891e25303babf1dd8633d6c58f74276`.
The raw file and parsed admission are retained outside source control at
`build/cfd-public-reference-20260907/`.

Citation: Driver, D. M. and Seegmiller, H. L. (1985),
[DOI:10.2514/3.8890](https://doi.org/10.2514/3.8890); NASA TMR Cf correction
dated 2015-10-17. Preserve source attribution with any derived evidence.

`admit_cfd_measured_reference.py` verifies the original-byte digest before
parsing. With a supplied prediction artifact it enforces case/normalization
identity and ordered finite coordinates, forbids extrapolation, and reports
absolute/RMS errors against a predeclared budget. Published error bars are
not assigned an invented confidence level or covariance. A comparison does
not prove its caller's geometry or solver-run provenance; those artifacts
must also be independently checked.

```powershell
python scripts/admit_cfd_measured_reference.py --reference build/cfd-public-reference-20260907/cf.exp.dat --output build/new-reference.json
```

Status: **measured reference admitted; SPIKE backward-step prediction and
measured correlation not yet executed**. Existing synthetic duct outputs
are not valid substitutes for this different geometry and Reynolds number.

## Selected thermal-flow dataset

[Parker and Smith, Utah State University (2020)](https://digitalcommons.usu.edu/all_datasets/126/)
is a heated plenum-to-plenum experiment with as-built geometry, inlet and
response measurements, temperature/pressure data, and uncertainty columns.
Its nine operating cases separate forced-flow and heating conditions.
The repository declares CC BY 4.0; attribution is required.
[DOI:10.26078/cad3-j806](https://doi.org/10.26078/cad3-j806).

Status: primary metadata reviewed and dataset selected, not yet imported or
simulated. Reconstructing its as-built thermal boundaries, sampling coordinates
and turbulence conditions is required before comparison. File-level download
and digest admission remain necessary; no measurements have been invented.

## Newer enclosure/fan project

[FAN-02, Zenodo record 17909944](https://zenodo.org/records/17909944)
is a 2026 enclosed centrifugal-fan benchmark from the FAU/Graz collaboration.
The inspected record exposes housing STEP geometry and sensor coordinates;
its description references additional measurement publications. It is a useful
candidate for future fan/enclosure and vibro-acoustic work, not a substitute
for a ready thermal-flow response dataset. License and complete operating-point
data must be verified before incorporating its assets.

## Qualification scope

Reference admission, parser tests and experimental-data availability are not
successful solver correlation. Promotion requires matching model/boundaries,
mesh/time convergence, uncertainty-aware comparison, and independent review.
No arbitrary-enclosure production flag is changed by this corpus.
