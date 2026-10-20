<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Optics, laser optics and spectral materials

Electron/ion lenses and TEM/SEM are a separate
[charged-particle/vacuum track](CHARGED_PARTICLE_VACUUM_PLAN.md). Photon Maxwell
propagation and matter-wave imaging must not be treated as interchangeable.

## Authorization and delivered boundary — 21 October 2026

The owner explicitly requested optical instrument, laser, interferometry and
material-interaction development across visible, UV, infrared/thermal and X-ray
bands. This supersedes the earlier development scheduling deferral for this
track, not numerical, provenance, human-review or release gates. PI/SI remains
primary. The legacy parity backlog retains planned OP01–OP05 stages until their
individual prerequisites and acceptance evidence are established; no stage is
marked Done by this authorization or by the first kernel below.

The first implemented increment is the internal, standalone C++20
`src/optics/planar_reference.*`: normal-incidence passive half-space Fresnel
amplitudes, absorption/forward power with depth, and a separate ideal coherent
balanced two-port. See the [derivation and executed verification](validation/NATIVE_OPTICS_REFERENCE_20261021.md).
It is not a spatial wave solver or instrument workflow. No optical worker,
public ABI, UI, spectral catalog, MPI/GPU backend or production claim is added.
Existing `optycal_suite` PEC far-zone scattering is a different approximation;
existing gray thermal-radiation solvers do not establish coherent optics.

## Model hierarchy and instrument requirements

Use the least costly formulation that resolves the requested observables.
Never discretize a meter-scale telescope uniformly at optical wavelengths.
Handoffs must preserve frames, phase reference, polarization, power and uncertainty.
Native C++ kernels follow the [shared native/HPC direction](NATIVE_HPC_MIGRATION.md);
Python remains orchestration, not a second numerical implementation. Parallel
FFT, domain decomposition and distributed Maxwell require measured scaling and
identical mathematical contracts before advertisement. WASM may later host
bounded previews, not silently substitute reduced physics for a qualified solve.

| Application | Required formulations and outputs | Separate qualification boundary |
| --- | --- | --- |
| Telescopes | Mirrors/aspheres, pupils/stops, optical path, diffraction, polarization, PSF/MTF, wavefront error, stray light and alignment | Obscurations, multireflection scatter and thermal/structural deformation need separate references |
| Microscopes | Illumination/coherence, lens trains, imaging transfer, aberrations and high-NA vector fields | Scalar/paraxial propagation does not qualify high-NA vector or sample-scattering imaging |
| Lithography optics | Mask diffraction, partial coherence, projection, polarization and aerial-image dose/intensity | An aerial image is not a printed resist feature; resist chemistry/process engineering is not authorized by this optical scope |
| Laser optics | Beams, polarization, coatings, cavities, modes, linewidth and resonator stability | Pump/gain, lasing, nonlinear/ultrafast response, damage and ablation need additional laws and validation |
| Virtual interferometry | Michelson/Mach–Zehnder/Fabry–Pérot paths, phase, beam splitters, detector integration, fringes and calibrated path recovery | Ideal unitary port algebra is not a spatial interferometer, finite-coherence source or detector/noise model |
| Thermal/IR optics | Spectral absorption, radiometry, coatings and absorption-to-heat | Emissivity/emission require explicit spectral/angular/polarization assumptions; near-field thermal radiation is distinct |
| X-ray/EUV optics | Complex-index attenuation, grazing mirrors, multilayers and crystal diffraction | Bulk attenuation does not model fluorescence, secondary particles, all scattering or dynamical crystal diffraction |

Required complementary engines: geometrical rays with Snell/reflection/TIR;
coherent scalar Fresnel/angular-spectrum propagation with sampling/window limits;
vector Maxwell FEM/FDTD/BEM or justified envelope/mode methods for wavelength-scale,
high-NA, resonant and anisotropic structures. Material dispersion must be causal
in time-domain studies. Each approximation must reject unsupported inputs.

## Spectral material contracts

Requested metals explicitly include **gold, silver, beryllium, aluminum and zinc**.
Also required are vacuum/gases, optical glasses, dielectrics, semiconductors,
crystals and deposited/coated multilayers. A chemical name is not an optical
model and a metal is not automatically a perfect conductor.

Each admitted dataset must bind identity to source/version/hash, redistribution
rights, measurement/model lineage, wavelength or photon-energy units, supported
band, complex sign convention, temperature, composition, density and uncertainty.
Record crystal axes, film/substrate thickness, oxidation, roughness and fabrication
conditions where applicable. Distinguish bulk, thin-film and surface-effective
properties. Optical/thermal/mechanical properties share identity and conditions,
not interchangeable constitutive laws.

No silent extrapolation, interpolation across unmeasured gaps/absorption edges,
or replacement of missing data with a constant index. Enforce passive data where
required. Finite-band samples alone cannot certify global Kramers–Kronig
consistency. Visible, UV/VUV/EUV, near/mid/far IR and soft/hard X-rays require
separately admitted bands. An X-ray index below unity is not a negative-index
metamaterial. Kirchhoff/emission work must match wavelength, direction and
polarization under its physical assumptions. **Emissivity is not universally
`1-R`: transmission may be nonzero, and normal incidence is not hemispherical
emission.** No emissivity algorithm or measured constants are supplied here.

Candidate data sources, not admitted dependencies or copied catalogs:

- [Polyanskiy, Scientific Data 11, 94 (2024)](https://www.nature.com/articles/s41597-023-02898-2), DOI `10.1038/s41597-023-02898-2`: peer-reviewed database descriptor. Review every underlying dataset and its rights/conditions separately.
- [CXRO optical constants](https://henke.lbl.gov/optical_constants/): Henke, Gullikson and Davis, *Atomic Data and Nuclear Data Tables* 54, 181–342 (1993), 50–30,000 eV, elements Z=1–92. Not visible-band coverage or universal material validation.
- [NIST EUV optical constants](https://www.nist.gov/programs-projects/extreme-ultraviolet-optical-constants): authoritative complex-index/attenuation context; no NIST data is bundled here.

## Checkable delivery stages

1. **Planar references (implemented, experimental):** phasor convention, E/H
   continuity, Fresnel power, Beer–Lambert attenuation and coherent unitary ports;
   independent analytical oracles and invalid-input tests. No coatings.
2. **Spectral admission and coatings:** reviewed real datasets/uncertainty; stable
   multilayer scattering composition, oblique s/p, TIR and absorbing-film R/T/A/phase;
   single-interface, quarter-wave and independent-solver references.
3. **Scalar propagation and virtual experiments:** Gaussian/plane-wave/slit/pupil
   references, FFT sampling/window refinement, phase/power budgets, finite
   coherence and Michelson fringe recovery. Add ray surfaces and detectors.
4. **Vector optics:** polarized Mie/interface/mode/cavity references, high-NA,
   mesh/order/time/PML refinement, passive dispersive fits and independent
   comparisons. A resonant peak alone does not establish modal Q.
5. **Instruments and STOP:** revision-bound assemblies, PSF/MTF/wavefront,
   absorbed-power-to-heat conservation, dn/dT, expansion/stress and deformed
   surfaces; experimental instrument correlation with uncertainties.

Every stage needs units, applicability, error budgets, failure cases, provenance
and executed evidence. Reference examples cannot qualify all metals/bands/devices.
Human review and clean Windows/Linux/package qualification precede release claims.

## Established and recent research review

The first increment derives Maxwell boundary and Poynting relations independently;
exact reviewed sections and convention mapping are in the method record. No
external implementation was inspected, copied or translated.

Recent peer-reviewed research candidates found during the 21 October search:

- [Generic full-vector angular spectrum method, 2025](https://doi.org/10.1088/2515-7647/ae0384): candidate vector propagation study. Publisher search metadata reviewed; full text blocked by robots policy. **Not implemented or fully reviewed.**
- [Resampled angular spectrum method, 2026](https://www.sciencedirect.com/science/article/pii/S0030401826006425): candidate sampling study. Publisher search snippet reviewed; full text returned HTTP403. **Not adopted.**

Novelty/citation counts are not acceptance evidence. Compare candidates with
established Maxwell/diffraction references and independent convergence/performance
measurements. This is not an exhaustive publication review through 2026.
