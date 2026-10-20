<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Native planar optics reference — 21 October 2026

Status: experimental internal mathematical reference, not production-qualified.
Scope and later stages: [optics/materials plan](../OPTICS_PHOTONICS_MATERIALS_PLAN.md).

## Independently authored governing derivation

Assume a smooth planar interface at z=0, normal incidence, linear local
homogeneous isotropic media with relative permeability 1. Incident index n0 is
real and positive; the half-space has N=n+iκ, n>0, κ≥0. Use
`E(z,t)=Re[E0 exp(i k z-iωt)]`, `k=2πN/λvac`. The same fixed tangential electric
field direction defines incident/reflected/transmitted amplitudes. Continuity gives
`1+r=t`, `n0(1-r)=Nt`, hence `r=(n0-N)/(n0+N)`, `t=2n0/(n0+N)`.

The forward cycle-averaged Poynting flux is `Re(N)|E|²/(2 Zvac)` for this
nonmagnetic normal wave. Consequently `R=|r|²`, `T0=(n/n0)|t|²` and
`R+T0=1`. **T0 is power entering the half-space, not slab transmittance.**
Positive κ attenuates field amplitude; intensity attenuation is
`α=4πκ/λvac` in m^-1. At depth z metres, forward incident-power fraction is
`P(z)=T0 exp(-αz)` and integrated absorption is
`A[0,z]=T0[-expm1(-αz)]`; `R+P+A=1`. No back surface, return wave, multilayer,
oblique angle, magnetic, anisotropic, gain or emissivity model is present.

The separate ideal two-port uses amplitudes in sqrt(W):
`[out1,out2]=[a+i b,i a+b]/sqrt(2)`. Its matrix satisfies `S†S=I`;
coherent complex amplitude sums precede power evaluation. This establishes
ideal port phase/power algebra, not a physical coating or spatial interferometer.
Equal-frequency coherent inputs and orthogonal output modes are assumed;
incoherent averaging is not implemented.

## Numerical analysis and admission

Scale n0,n,κ before complex division and squared norms; compute entering power
from the direct positive expression, not cancellation-prone `1-R`.
Use `expm1` to retain tiny positive absorption. Zero κ/depth has exact zero
absorption. At optical depth≥700, report zero forward power and absorption T0
with a separate conservative absolute fraction error bound: upward-rounded
`T0*1e-300`, since `exp(-700)<1e-300`. This explicit opacity approximation is
not renormalization. Fixed incident-power closure gate: 1e-12; ideal ports use
a scaled relative power gate 1e-12.

Reject nonfinite values, negative extinction/gain, index outside [1e-12,1e12],
κ outside [0,1e12], vacuum wavelength outside [1e-15,1e3] m or depth outside [0,1e6] m.
Positive attenuation or optical depth that cannot be represented fails closed.
Port real/imaginary components must be finite and at most 1e100 in magnitude;
unresolvable rounded output power fails closure. These are numerical admission
bounds, **not physically validated spectral/material intervals**.

## Exact primary-source review and provenance

- [MIT6.974, electromagnetic waves/interfaces, spring2006](https://www.ocw.mit.edu/courses/6-974-fundamentals-of-photonics-quantum-electronics-spring-2006/fafcb9e36b7749f4eeb099d666bdf70a_electr_wav_inter.pdf): reviewed §2.2.3, printed pp47–51, equations2.108–2.115 and boundary/power discussion. Its opposite temporal/spatial phasor convention is mapped above. Educational derivation, not recent peer review.
- [Byrnes, *Multilayer optical calculations*, arXiv1603.02720v5](https://arxiv.org/html/1603.02720v5), revision30December2020: reviewed §§2–2.2 and4.3–4.5, equations17–24 for convention, power and absorption. Technical preprint, not labeled peer-reviewed. Lossy incident media are excluded. Linked implementation not inspected.
- [Polyanskiy2024](https://www.nature.com/articles/s41597-023-02898-2): reviewed abstract/background and methods introduction for complex index, nonmagnetic permittivity, attenuation and dataset provenance limits. Peer-reviewed descriptor; no table or software copied.
- [NIST EUV](https://www.nist.gov/programs-projects/extreme-ultraviolet-optical-constants): reviewed complex-index and attenuation definitions. No constants imported.

Code, scalar oracles, boundary checks and prose were independently authored.
Public governing mathematics is referenced, not claimed as a new invention.
No external numerical implementation was copied or translated, no dataset was
admitted and no general legal guarantee of plagiarism absence is asserted.

## Executed verification

On this Windows host: GNU g++ 16.2.0 (MSYS2 UCRT), CMake 4.2.1, Ninja, Release and Debug;
C++20, warnings-as-errors, `-fno-fast-math -ffp-contract=off`.
CTest passed **1/1 in each configuration**; the test executable passed
**408 active checks** per invocation.
Checks are exception-based and remain enabled under NDEBUG/Release.
Retained local output: `build/native-optics-20261021/test-summary.json`.
Machine/toolchain/source/binary SHA-256 evidence is retained locally in
`build/native-optics-20261021/build-evidence.json` (SHA-256
`4f99cddb6dbf01ede72daa1c4d58e0511c9e1331ec436e49448d16e76267ae54`).
These local artifacts are not a signed release package.

Tests independently expand rational Fresnel powers in long double and check
electric/magnetic boundary residuals; cover matched, lossless, absorbing,
sub-unity and extreme indices, synthetic wavelengths, zero/tiny/opaque depth,
splitting, bright/dark interference, arbitrary complex coherent inputs,
unitarity and invalid/unrepresentable inputs. Synthetic X-ray-sized wavelengths
do **not** qualify an X-ray material or scattering workflow. No measured optical
data, independent optical package, mesh or instrument correlation was run.

Reproduce from the repository root with GNU/Ninja available on PATH:

```powershell
cmake -S src/optics -B build/native-optics -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/native-optics
ctest --test-dir build/native-optics --output-on-failure
./build/native-optics/test_native_optics_reference.exe build/native-optics/summary.json
```

Standalone build intentionally avoids legacy top-level fast-math flags.
MSVC/Linux/sanitizer/MPI/packaged execution and knowledgeable human numerical
review remain open. No public capability manifest or production gate changed.

Repository architecture check passed during this increment. The separate parity
backlog check failed with `PI/SI evidence stale or foreign` while its owner was
replaying existing source-bound gates against concurrently changed inputs.
No receipt hashes, acceptance thresholds or stage statuses were changed here;
this optical check is not a green full-suite/release qualification claim.
