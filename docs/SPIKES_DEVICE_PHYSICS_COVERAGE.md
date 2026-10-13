<!-- SPDX-License-Identifier: Apache-2.0 -->
# Circuit-level device physics coverage

SPIKES targets compact, lumped device equations, including residual currents,
terminal charge, derivatives and coupled physical states. This is not spatial
Poisson/drift-diffusion TCAD, a process simulator, or automatic physics accuracy
from a symbol or material name. Manufacturer models and foundry PDKs require
applicable parameters, rights and separate qualification.

## Current bounded support

| Device/interface | Executable scope | Important exclusions |
| --- | --- | --- |
| Native NMOS D/G/S/B | Level-1 channel/body threshold; CGS/CGD/CDS under BE/BDF2 | Core has no bulk junction current/charge; forward body threshold is clamped |
| Generic NMOS4 subcircuit | Adds explicit bulk junction diodes and constant CGB/CBD/CBS | No depletion law, recovery, avalanche or process qualification |
| Native NPN C/B/E | Ebers-Moll and bounded CBE/CBC/TF/TR charge under BE/BDF2 | No native fourth-terminal substrate model |
| Generic NPN4 subcircuit | Explicit collector-substrate diode/capacitor around the three-pin core | Not a production substrate-transport, latch-up or BiCMOS model |
| BSIMBULK/CMG | Existing pinned OSDI bindings; specific model/runtime restrictions apply | Not arbitrary foundry compatibility; temperature-rise port grounded in current Python binding |
| PNP/PMOS/JFET/dual gate | New explicit terminal symbols | Geometry alone does not add native model support |
| Substrate resistor / feedthrough / Kelvin | Explicit linear RLC/leakage/contact networks | No material transport, dielectric relaxation, aging, thermal or frequency-range qualification |
| Coupled-inductor symbol | Explicit winding terminals and polarity dots | No new saturating/core-loss physical model introduced by this symbol |

See [the model API, derivation and native tests](SPIKES_LUMPED_PHYSICS_PARTS.md).
Hybrid trapezoidal is deliberately unavailable for the bounded charged native
transistors; select a documented analysis explicitly, never silently substitute.

## Remaining physics/part workflow completion

- Production MOS/BJT families need correct polarity, geometry, temperature,
  junction/body/substrate charge, diffusion charge, high-injection/breakdown,
  noise and validity envelopes. Charge conservation and Jacobian checks must
  accompany transient and small-signal qualification.
- BiCMOS/SOI/GaN/SiC and future materials are process/model-package questions,
  not a universal family toggle. Shared wells/substrates, isolation, guard rings,
  parasitic bipolar paths, substrate RC and thermal coupling need explicit
  topology and applicable measured or foundry parameters.
- Passive physics needs declared constitutive R(T,V,I), Q(V,T,state) and
  flux-linkage/current/state relations: dielectric absorption/bias, skin and
  proximity effects, hysteresis/core loss, saturation and thermal feedback.
  Conservation, positive/negative differential behavior and validity limits
  must be tested for each admitted model rather than appended cosmetically.
- Multi-terminal plugins require terminal/domain identity, current and charge
  accounting, derivative/sparsity contracts, lifecycle/checkpoints, noise and
  observables. Existing metadata registration is not universal executable
  device-plugin stamping.
- Full graphical subcircuit-instance placement and model/pin/physical-package
  mapping remain separate from the present symbol editor and subcircuit export.

Original symbols use unverified common conventions. Bulk arrows follow P-to-N
junction direction; facts were checked against
[MIT 6.101 Lecture 6, slide 12](https://web.mit.edu/6.101/www/s2020/handouts/L06.pdf).
The code and geometry were independently authored; no external artwork or
implementation was copied. Numerical human review is required before release.
