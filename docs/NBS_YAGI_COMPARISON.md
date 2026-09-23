<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Exploratory solver-to-measurement comparison

`scripts/run_nbs_yagi_comparison.py` executes installed openEMS FDTD; it does not
replay measured S-parameters. New outputs are immutable directories. The worker
has a three-million-cell pre-run cap, two threads, 900-second timeout and 1-GiB
artifact ceiling. These are process/resource bounds, not an OS memory limit.

```powershell
python scripts/run_nbs_yagi_comparison.py --output build/nbs-yagi-new --mesh-mm 20
python -W error -m unittest tests.python.test_antenna_measured_comparison -q
```

The measured source is Peter P. Viezbicke, NBS Technical Note 688, Table 1 and
measurement-method section, [DOI 10.6028/NBS.TN.688](https://doi.org/10.6028/NBS.TN.688).
Its 0.4-wavelength antenna has reflector length 0.482 wavelength, director length
0.424 wavelength, 0.2-wavelength spacings and 0.0085-wavelength element diameter.
Reported gain is 7.1 dBd at 400 MHz, estimated accurate within 0.5 dB. The report
instructs adding 2.16 dB for an isotropic reference: 9.26 dBi.

The authored model deliberately records its differences: straight PEC half-wave
driven wire instead of the measured folded dipole and tuner; free space instead
of the ground range; omitted plexiglass support. This is therefore exploratory
discrepancy evidence, **not geometry-matched validation**. Mesh convergence and
combined numerical/measurement uncertainty are also required for qualification.

The output distinguishes forward directivity (radiated-power denominator) from
accepted-power gain. It does not call either quantity mismatch-inclusive realized
gain. The measured antenna was impedance matched; no arbitrary S11 correction is
applied to its measurement. Even numerical agreement cannot promote qualification.

Primary PDF retained locally at
`build/nbs-yagi-primary-20260907/nbstechnicalnote688.pdf`, SHA-256
`78ac6bf88302591dcc7ae9d03719f66adc5461cf05a43f0414fd1a03cbc85413`.
Table 1 was visually checked against that original. The primary is a US federal
government publication; no third-party solver implementation was copied.

## Executed result

`build/nbs-yagi-fullpulse-20260907` reached -50.70 dB field-energy decay after
8954 iterations in 257.77 seconds on 327250 actual FDTD cells. Accepted-power
forward gain was 9.418837 dBi, a +0.158837 dB difference from the published value.
Forward directivity was 9.400580 dBi; radiated/accepted power was 1.004213.
These satisfy this run's temporal and five-percent PEC power-balance checks,
not mesh convergence or matched-geometry qualification.

The immutable original `solver-result.json` used raw Fourier spectral products
in its two power fields. Their absolute watt labels were incorrect; ratios and
gain were unaffected. **Use `power-normalization-correction.json` for powers**:
one watt incident gives 0.356082 W accepted and 0.357582 W radiated. This sidecar
was recomputed from retained actual port traces and binds their hashes. The
current worker normalizes these fields before publication. The worker's original
conservative temporal flag is superseded only by the separate hashed host
`numerical-admission.json` log evaluation, not by editing the original file.

Earlier directories retain a timeout failure and an incomplete-excitation run;
the latter explicitly failed numerical admission. Their spectra are not usable
physical comparison results. No geometry or material was fitted to the measured
gain during these runs.
