<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Electron/ion optics, vacuum and kinetic environments

## Owner-requested scope — 21 October 2026

The owner has requested electron/ion optics for TEM, SEM, scatter sensors,
accelerating anodes/cathodes, focusing rings and interactions with surroundings
from sparse vacuum through hypobaric and hyperbaric conditions. This activates
bounded development of the previously horizon particle/vacuum track, not a
claim that the complete instrument or pressure range is supported. Existing
PI/SI priorities, numerical acceptance, data rights and release review remain.
No parity status or public runtime capability is promoted here.

Photon optics and electron/ion optics share geometry, fields, material identity
and diagnostics but **not the same propagation equation**. Charged trajectories
use relativistic Lorentz dynamics; coherent electron imaging requires a justified
matter-wave/specimen interaction formulation. Maxwell optical propagation alone
does not produce a TEM image. This track complements the
[optics/materials plan](OPTICS_PHOTONICS_MATERIALS_PLAN.md),
[mechanics/device plan](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md) and
[native/HPC roadmap](NATIVE_HPC_MIGRATION.md).

The initial internal native reference belongs to `src/particles/`, with
`tests/test_native_particle_reference.cpp` and its
[method/verification record](validation/NATIVE_PARTICLE_REFERENCE_20261021.md).
Its bounded quantities are relativistic energy/momentum/speed/wavelength,
signed electrostatic energy change, dilute hard-sphere gas mean-free-path/time
and Knudsen diagnostics, and supplied stationary-target beam attenuation.
These are not spatial trajectories, Brownian dynamics, stress, PSF/FWHM,
SEM/TEM or pressure-vessel workflows. No measured scattering data is bundled.

## Physical models and regime selection

| Problem | Governing formulation and required inputs | Important boundary |
| --- | --- | --- |
| Anodes, cathodes, apertures and focusing rings | Conforming conductor/insulator/vacuum geometry; electrostatic potential/field, magnetostatic lenses and relativistic Lorentz tracking | Charge sign, electrode potentials, finite edge/tip radii, contact and material data are explicit; no invented emission area or lens law |
| Beam emission and collective response | Supplied emission distribution first; later qualified thermionic/field emission, Poisson/space-charge iteration and PIC where justified | Emission, secondary yield, charge deposition and beam self-fields need separate laws; a test-particle solve has no space-charge capability |
| SEM/scatter sensors | Beam/specimen transport with energy/angle-dependent elastic and inelastic processes, detector acceptance/efficiency, signal integration and noise | Geometric beam survival is not secondary/backscatter yield, electron-beam heating or an SEM image |
| TEM and electron interferometry | Relativistically conditioned wavelength, coherent illumination, objective aberrations, diffraction, specimen potential/crystal orientation and validated wave/scattering methods | Multislice/Bloch-wave or other matter-wave methods need their own derivation, sampling, thickness and scattering evidence |
| Ion optics | Supplied mass, charge state, energy/spread, electrostatic/magnetic transport and material-specific ion stopping/scattering | Electron cross sections cannot be reused for ions; charge exchange, sputtering, implantation and secondary emission require additional data/models |
| Collisionless/free-molecular environment | Ballistic transport, wall interaction/accommodation, pumps/sources and residence times | A zero-collision model is explicit; numeric gas formulas do not encode infinity as a fabricated finite mean free path |
| Rarefied/transitional gas | Boltzmann/DSMC or qualified kinetic methods, species/cross sections, wall accommodation, local density/temperature and length/time scales | Cell/time resolution and statistical uncertainty must be checked; pressure alone does not establish the regime |
| Continuum and dense environments | Compressible mass/momentum/energy, justified EOS/transport, slip or no-slip and heat transfer as applicable | Dilute ideal hard spheres do not qualify dense gas, high-pressure real-fluid, phase-change or hyperbaric structural behavior |
| Brownian/dispersed motion | Inertial/overdamped Langevin or kinetic coupling with calibrated drag and fluctuation-dissipation | Continuum Stokes drag is not valid across all Knudsen numbers; small molecules, colloids and charged beams are not interchangeable particles |

Keep absolute pressure in Pa separate from gauge pressure and external-pressure
reference. Hypobaric/hyperbaric are operating descriptions, not solver models.
Regime selection must consider local Knudsen number, density/packing, EOS,
relativistic/degeneracy conditions where relevant, Mach/Reynolds, temperature,
composition, wall scales and measurement uncertainty. Mixtures and moving thermal
targets require velocity-averaged collision rates, not a universal constant sigma.

Chemical-process modeling remains outside active scope except the existing
propulsion exception. This request does not silently activate reactive plasma,
gas-discharge, ionization chemistry or a general chemical reaction network.
These would need explicit scoped authorization and species/energy evidence.

## Analytical and diagnostic outputs

- **Kinetics/beam:** signed charge and species, kinetic energy (J/eV), momentum
  (kg m/s), velocity (m/s), relativistic gamma, de Broglie wavelength (m),
  time of flight, phase space, current, transmission/loss and emittance/brightness.
- **Collisions:** number density (m^-3), cross-section provenance (m^2 or
  m^2/sr), process-resolved rates (s^-1), free path (m), free time (s),
  angular/energy distributions and confidence intervals. Distinguish gas-gas
  mean-free-path from beam-through-target attenuation; their factors differ.
- **Imaging:** calibrated detector coordinates, PSF/line spread, encircled energy,
  MTF/contrast transfer, focal shift and chromatic/spherical aberrations. FWHM is
  defined per declared profile/axis; multiple peaks may have multiple crossings.
  Do not report `2.355*sigma` as a universal measured PSF width.
- **Brownian:** displacement moments/MSD, diffusion, velocity autocorrelation,
  equilibrium covariance, relaxation time and stochastic convergence/error bars.
  Reproducible random streams must remain valid under rank repartitioning.
- **Coupled surroundings:** deposited charge/energy, momentum flux, gas and wall
  temperatures, heat transfer, structural traction/stress/deformation and optical
  misalignment. Scalar gas pressure alone does not establish wall stress or beam
  momentum transfer. Transfers must conserve the applicable power/charge/work.

Use distributions and uncertainty where the physics is stochastic. A small
sample of rays, a smooth plot or a converged linear residual is not evidence of
instrument resolution, detector yield or continuum/kinetic convergence.

## Checkable development order

1. **Native analytical foundation:** energy/momentum and charge-sign tests;
   separately defined dilute-gas and stationary-target collision quantities,
   nonfinite/unit/range/applicability rejection. Synthetic inputs only.
2. **Collisionless field-to-beam:** geometry-bound E/B interpolation, boundary
   events, relativistic tracking, electrostatic lens references, uniform-E/B and
   crossed-field oracles, time/mesh convergence and charge/energy diagnostics.
   Verify cathode/anode polarity and aperture interception before SEM claims.
3. **Collisional/rarefied environment:** reviewed cross-section records, distinct
   elastic/inelastic processes, stochastic sampling and detailed balance where
   applicable; DSMC/kinetic wall/flow references and sample/time/cell convergence.
4. **Imaging and sensors:** qualified incident beam plus detector and specimen
   models; independent focusing/aberration/PSF/MTF and measured SEM/TEM/scatter
   fixtures with input uncertainties. Coherent TEM remains a separate substage.
5. **Pressure/Brownian/multiphysics:** continuum-to-kinetic comparisons, real-EOS
   and equilibrium limits, Brownian analytical/statistical references, conservative
   thermal/charge/structural coupling and measured pressure/environment fixtures.

Native C++ owns numerical execution. Python contracts will carry species,
fields, geometry, statistics and provenance through the existing worker;
do not add physics to Rust/TypeScript. Ensemble parallelism precedes distributed
self-consistent PIC/DSMC; charge deposition, halo exchange, collision pairing,
reduction determinism and scaling must be independently qualified. No cluster,
GPU or WASM capability is enabled by this roadmap.

High-voltage, radiation and pressure hardware certification remain separate
from numerical verification. No simulated instrument image certifies safe
hardware operation.

## Research and data lineage

Established governing relations are implemented independently; see the method
record for exact reviewed portions. Recent methods are evaluated against them,
not accepted merely for novelty or citation counts.

- [NIST SRD64 version5.0 guide, December2023](https://doi.org/10.6028/NIST.NSRDS.64-2023): reviewed introduction pp1–3 and units/scope discussion. Electron elastic scattering only; the guide distinguishes the sampler's energy scope from the broader cross-section scope. Its copyright/redistribution statement must be reviewed before any database admission. **No data, algorithm implementation or sampler copied/adopted here.**
- [Hairer, Lubich and Shi, SIAM J. Numer. Anal.61(6),2844–2858 (2023)](https://doi.org/10.1137/23M1568946): publisher abstract/history reviewed, not paywalled full method. Candidate structure-preserving relativistic integrators; **not implemented**.
- [Moment-preserving Monte-Carlo Coulomb collision method, JCP531,113927 (2025)](https://doi.org/10.1016/j.jcp.2025.113927): primary OSTI/publisher search metadata reviewed; full text retrieval failed. Candidate only, **not adopted or claimed fully reviewed**. Coulomb collisions are not neutral hard-sphere scattering.

Record exact data versions/hashes, rights, species/charge state, target phase,
energy/angle bands, units, density/temperature and uncertainties on admission.
Reject unsupported extrapolation and distinguish total, momentum-transfer and
differential cross sections. No public database is assumed freely redistributable
merely because a web page can be read.
