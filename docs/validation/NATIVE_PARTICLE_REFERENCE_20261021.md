<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Native particle/kinetic reference — 21 October 2026

Experimental internal mathematical reference; no public worker/ABI/manifest
or production capability promotion. [Full requested scope](../CHARGED_PARTICLE_VACUUM_PLAN.md).
Implementation: `src/particles/kinetic_reference.*`; tests:
`tests/test_native_particle_reference.cpp`. Executed evidence below applies
only to this bounded reference, not the broader scope plan.

## Independently authored governing derivation

### Relativistic kinematics and electrostatic work

For supplied positive rest mass m and kinetic energy K>=0, total energy is
`E=K+mc^2`; the invariant `E^2=(pc)^2+(mc^2)^2` gives
`p=mc sqrt(u(u+2))`, `gamma=1+u`, `v=c sqrt(u(u+2))/(1+u)` with `u=K/(mc^2)`.
These avoid subtracting nearly equal rest and total energies. The matter-wave
diagnostic is `lambda_db=h/p`; it is absent at rest, not returned as zero.
It does not solve a wave equation or predict image resolution.

Conservative electrostatic work gives
`K_final=K_initial+q*(V_start-V_end)` with signed charge q in C and potential
in V. Electron acceleration to higher potential has q<0 and positive work.
Negative final energy is rejected: turning trajectories, geometry and emission
are not solved. Near-cancellation must be resolved or explicitly rejected,
not clamped into a transmitted particle at zero energy.

### Dilute gas versus beam-through-target collisions

For a single-species classical equilibrium ideal gas with supplied hard-sphere
diameter d, `n=p/(kB*T)`. Maxwell speed integration gives
`vbar=sqrt(8*kB*T/(pi*m))`. The mean relative speed of two identical equilibrium
particles is `sqrt(2)*vbar`; with `sigma=pi*d^2`, the mean collision rate is
`sqrt(2)*n*sigma*vbar`. Thus `lambda_gas=1/(sqrt(2)*n*sigma)`,
`tau_gas=lambda_gas/vbar`, `Kn=lambda_gas/L`.
Pressure is absolute Pa, temperature K, lengths m, mass kg; lambda and tau
are m and s. This hard-sphere result is not a real-species collision database.

In contrast a test beam of fixed speed through independent stationary targets
with supplied number density n and total cross section sigma has
`dP_uncollided/ds=-n*sigma*P_uncollided`. Therefore
`lambda_beam=1/(n*sigma)`, `tau_beam=lambda_beam/v`, and probability of at least
one collision along s is `-expm1(-n*sigma*s)`. There is **no sqrt(2)** factor.
No angular deflection, energy loss or secondary production is computed. A moving
thermal target requires relative-velocity averaging and possibly energy-dependent
cross sections; do not reuse this formula as a universal electron-gas law.

### Applicability and conditioning

Mass bounds [1e-32,1e-20]kg and kinetic energy [0,1e-6]J are numerical admission
limits. Require `K/(mc^2)<=1e6` and representable subluminal positive speed for
K>0. Constants use NIST 2022 CODATA: c=299792458 m/s, h=6.62607015e-34 J*s,
kB=1.380649e-23 J/K, e=1.602176634e-19 C (exact SI values), and electron mass
9.1093837139e-31 kg with standard uncertainty 2.8e-40 kg. Numerical test tolerances
are not physical-constant or experimental uncertainty.

The ideal gas reference rejects zero pressure, excessive hard-sphere packing
`eta=pi*n*d^3/6>1e-4` and excessive relativistic thermal parameter
`theta=kB*T/(mc^2)>1e-4`. These are conservative declared applicability cutoffs,
not a theorem bounding real-gas/quantum/chemical error. Temperature/composition
may invalidate the model even within these checks. Quantum degeneracy is not
tested or modeled: these two cutoffs alone do not certify Maxwell statistics.
No dense EOS or phase diagram
is inferred. Kn is returned without a pressure-only automatic solver selection.
The requested high-pressure/hyperbaric workflows remain separate development.

Use `expm1` for tiny beam collision probability. For optical depth>=700, an
explicit opaque approximation reports survival 0 and collision probability 1 with
absolute probability error bound 1e-300. This does not infer absorption, heating
or a physical stopping range. Finite/range/representability checks apply before
returning numerical diagnostics; no acceptance threshold is relaxed.

For electrostatic work, compensated potential subtraction and FMA reduce
roundoff. Require final-energy resolution above `64*epsilon` relative to
`K_initial+abs(work)` unless represented exact cancellation is certified from
subtraction/product residuals. Nonzero subnormal work is rejected. Exact-zero
certification additionally requires work magnitude at least `2^-968` J (or
identical potentials), so an underflowed residual cannot falsely prove exactness.
The scalar energy balance does not certify passage through an electrode geometry.

## Reviewed primary foundations and provenance

- [MIT8.033 relativistic dynamics handout](https://ocw.mit.edu/courses/8-033-relativity-fall-2006/e05effec399aa480b6452ad9ca2ecabc_dynamics.pdf), Max Tegmark, revised 25 October 2005, distributed in fall 2006 course: reviewed PDF pp2–3 formula/momentum-energy summaries and p5 work-energy theorem. Supports invariant, velocity and work relations; no external implementation examined.
- [MIT5.62 lecture31](https://ocw.mit.edu/courses/5-62-physical-chemistry-ii-spring-2008/f90a4c878e68f44e42b85dbbd4d18751_31_562ln08.pdf), spring2008, revision24April2008: reviewed printed pp1–2 free path/time, dilute hard-sphere assumptions and distribution, plus pp3–4 momentum/heat transport context. The dense-gas heuristic is not implemented; no illustrative data copied.
- [NIST CODATA2022 complete table](https://physics.nist.gov/cuu/Constants/Table/allascii.txt): reviewed electron mass and the c,h,e,kB entries. No claim that the electron mass is exact.
- [deBroglie1929 original lecture](https://www.nobelprize.org/uploads/2016/04/broglie-lecture.pdf): original wavelength-momentum source identified and indexed equation excerpt reviewed; full PDF returned HTTP403. This review limit remains explicit before release review; no lecture prose/data copied.

Established mathematics, code, fixture inputs and test oracles are independently
authored. No external solver, sampler, mesh, cross-section dataset or source code
was inspected/adapted. Candidate recent research and data-rights boundaries are
recorded separately in the scope plan; candidates are not claimed implemented.

## Verification and open qualification

Executed on this Windows host using GNU g++ 16.2.0 (MSYS2 UCRT), CMake 4.2.1
and Ninja, C++20, warnings-as-errors, `-fno-fast-math -ffp-contract=off`:
**209 active checks passed in each of Release and Debug; CTest 1/1 per build.**
The independent long-double energy/momentum/speed checks include 16 additional
mass/energy combinations down to 1e-200 J, low-energy limit and TEM-like 200 keV
electron scale checks. Signed electron/ion work, turning/cancellation rejection,
pressure scaling, gas-versus-beam rate distinction, tiny/opaque probability and
opacity-threshold checks passed. These are analytical references, not trajectory
or gas-flow convergence studies. No experimental cross sections were used.

The unchanged earlier native optical Release regression also passed CTest 1/1
(408 checks). Architecture and parity-backlog consistency checks passed; the
backlog check verifies tracking/evidence integrity, not optical/particle physics.
No complete repository/full-release
qualification is claimed by these focused runs.

Local output: `build/native-particles-20261021/test-summary.json`. Source/binary
SHA-256, machine and compiler metadata are retained in
`build/native-particles-20261021/build-evidence.json`, SHA-256
`bb289a87b15f1bba98e583455478ea83c77bf205618b02c960f937b6a9e8eab4`.
This is local verification evidence, not a signed release package. Reproduce
from the repository root with GNU/Ninja on PATH:

```powershell
cmake -S src/particles -B build/native-particles -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/native-particles
ctest --test-dir build/native-particles --output-on-failure
./build/native-particles/test_native_particle_reference.exe build/native-particles/summary.json
```

The same standalone CMake source supports a separate Debug build. This isolated
target avoids legacy top-level fast-math options; it is not yet part of the
packaged solver runtime. Tests use exceptions, not disabled Release assertions.

No Brownian trajectory, gas stress, detector PSF/FWHM, space charge, focusing
ring field, specimen interaction, SEM/TEM image, DSMC/PIC or dense/high-pressure
workflow is delivered by these scalar reference kernels. Human numerical review,
independent solver/measurement correlation, MSVC/Linux/package and distributed
qualification remain open.
