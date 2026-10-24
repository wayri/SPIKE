<!-- SPDX-License-Identifier: Apache-2.0 -->
# Explicit AC resistor / retained solid / creeping-fluid heat bridge

## Scope and source API

`python/spike_core/em_network_resistor_cht.py:run_em_network_resistor_cht`
is an experimental **in-process source API**, not an installed worker route or
production capability. It composes `solve_em_network_ac` with
`solve_cfd_tetra_cht`; it does not replace their equations or acceptance gates.
See [ADR 0135](../adr/0135-explicit-network-resistor-to-creeping-cht.md).

Input is plain finite JSON with exactly:

- `contract`: `spike/em-network-resistor-cht-request/v1`;
- `ac_request`: existing explicit RMS/common-positive-real-reference request;
- `cht_request`: existing retained SI tetra mesh/identity/flow/energy request;
- `sample_index`: integer index selecting one supplied frequency;
- `resistor_cell_weights`: every named AC port maps to null (outside) or a
  nonempty object of canonical zero-based retained cell indices and fractions.

Example mapping: `{"p0":{"0":0.25,"1":0.75},"p1":null}`. Both cell indices
must identify declared **solid** cells. Fractions must sum to one within 1e-12;
they are not renormalized. Initial volumetric sources must all be exactly zero,
preventing double counting. Inputs are privately snapshotted, never modified.
Geometry, layer, net, device location and thermal contacts are not inferred.

Output retains the full AC and CHT results, per-cell watts, selected frequency,
deposited/outside resistor power, separately unclassified network power, input
and mesh digests, and limitations. The result is always experimental and
`production_qualified=false`. Source/mesh identity follows the existing CHT
owner; its `source_authenticity_verified=false` is preserved.

## Independent composition derivation and provenance

The [existing sampled-network derivation](../EMERGE_COSIMULATION.md) records
Kurokawa, *Power Waves and the Scattering Matrix*, IEEE TMTT 13(2), 1965,
[DOI 10.1109/TMTT.1965.1125964](https://doi.org/10.1109/TMTT.1965.1125964),
with its limited reviewed pages/equations. No new network representation or
field-amplitude calibration is introduced here. The existing
[RT0/P0 energy derivation](CFD_TETRA_ENERGY_20261021.md) defines its tetrahedral
conduction and shared-face donor enthalpy equations and primary sources.

New composition, independently derived: the external series resistor at port p
dissipates `P_p=Re(Zs_p)*abs(I_rms_p)^2` watts. RMS phasors require no factor
one-half. For declared fractions w_pc and SI tetra volume V_c, define
`P_c=sum_p w_pc P_p` and `q_c=P_c/V_c` W/m3. Null destinations contribute to
P_outside instead. Therefore `sum_c q_c V_c + P_outside = sum_p P_p`.
The wrapper certifies both this allocation identity and the actual accepted CHT
integrated source, each at relative 1e-10, with exact zero handling. It uses
compensated sums for overlapping device contributions. No EM-network deficit,
reactive power, radiation or unrelated frequency sample becomes heat.

The source-integral and conservative face-flux foundation was reviewed on
23 October 2026 in NIST **FiPy 4.0.3**, mathematical documentation updated
18 June 2026: [discretization equations (2) and (4)](https://pages.nist.gov/fipy/en/stable/numerical/discret.html)
and [upwind equation (3)](https://pages.nist.gov/fipy/en/stable/numerical/scheme.html).
Only mathematical semantics were used, not FiPy code, examples or meshes. Its
orthogonality-dependent diffusion approximation is not used. Derivation,
implementation, mesh generators, oracles and prose are independently authored.

## Independent temperature oracle

The synthetic unit-cube domain has solid x<1/2 (k=2 W/m/K) and fluid x>1/2
(k=1 W/m/K). Zero flow supplies the conduction limit of the same CHT owner.
Exterior x planes are 300 K and remaining planes are insulated. A 20 V RMS
Thevenin source with external R=50 ohms drives a matched 50-ohm network:
I=0.2 A and **only the external resistor's 2 W** is deposited uniformly in the
half-volume solid (q=4 W/m3). The network's separate 2 W stays unclassified.

Independently integrate `-k T''=q` on the solid and `-k T''=0` on the fluid.
For a=1/2, define
`A=q*(a*a/(2*ks)+a*(1-a)/kf)/(a+ks*(1-a)/kf)` and
`B=(ks*A-q*a)/kf`. Then Tsolid=300+A*x-q*x*x/(2*ks) and
Tfluid=300+B*(x-1). These satisfy exterior temperatures and continuity of T
and normal Fourier flux. Compare **cell means**, using
`E[x*x]=(sum(x_i*x_i)+(sum x_i)^2)/20` on each tetra, not nodal samples.

A second family uses solved fluid velocity `u=(0,0.005*(x-a),0)` m/s,
which is harmonic, divergence-free and zero at the stationary interface.
Since T=T(x), `u.grad(T)=0` and the same exact solution applies. Insulated
lateral boundaries prescribe its explicit incoming triangle-average
temperature (second-moment denominator 12); the benchmark asserts nonzero
solved mass flux. Area-average inlet T is not generally the mass-flux-weighted
average; ordinary boundary discretization error is included in refinement.
This exercises transport and mapping, not thermally active advection/cooling.

Predeclared gates: each observed refinement order >=0.8, finest volume-weighted
relative L2 temperature-**rise** error <=0.05, plus unchanged child mixed residual
<=1e-10 and cell/global energy defects <=1e-9. No baseline-300 K normalization.

Executed `scripts/benchmark_em_network_cht.py --output build/em-network-cht-refinement-r2-20261023`
using `.venv/Scripts/python.exe` and BLAS/OpenMP threads=1:

| Family | Cells | Relative L2 rise error | Observed order | Maximum cell energy defect |
| --- | --- | ---: | ---: | ---: |
| Zero flow | 12 | 0.59794422 | - | 3.33e-16 |
| Zero flow | 96 | 0.13398975 | 2.158 | 4.26e-15 |
| Zero flow | 768 | 0.03183281 | 2.074 | 4.47e-14 |
| Tangential shear | 12 | 0.59740227 | - | 9.99e-16 |
| Tangential shear | 96 | 0.13374411 | 2.159 | 2.52e-15 |
| Tangential shear | 768 | 0.03170820 | 2.077 | 2.85e-14 |

All gates passed; maximum mixed residual was 6.26e-14, global relative energy
defect 2.23e-16. The coarse mesh's large error is retained, not hidden. These
are synthetic conduction/tangential-flow results, not evidence of arbitrary physical
enclosure cooling. Separate tests exercise nonzero solved flow with deposited
solid heat, multiport unequal loss/nonuniform overlapping mappings, port-order
permutation, outside loss, purely reactive boundaries, no sweep summation,
invalid/double-counted heat, early/late/child cancellation and forged tickets.

The R2 `report.json` SHA-256 is
`f525e0a5ca4fe05ead5069dd5300aa7c6da275e6482d532a7e22f7853be62d0e`.
Its inspected implementation sources remained unchanged throughout execution;
12 request/result artifacts have recorded digests. Earlier zero-flow-only
evidence remains separately retained, not overwritten. A 46-test integration
run and a 103-test broader CFD/AC-PI/thermal/SI regression run passed, zero skips
(11 bridge tests overlap those runs). Architecture validation passed. Independent
mathematical/security review identified resource admission and multiport-oracle
gaps; both were corrected and rerun. Review found no remaining actionable defect
within this scope; knowledgeable human release review is still required.

## Resources, use and limitations

Reproduce from source (tests supply the independently authored fixture builder):

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_em_network_resistor_cht -v
.venv/Scripts/python.exe scripts/benchmark_em_network_cht.py --output build/new-ac-cht-benchmark
```

The benchmark requires a fresh output directory and retains each request/result,
artifact hashes, inspected source hashes and a report. Source drift fails it.
It is not an installed-app tutorial or a rebuilt worker.

The subsequent [24 October alpha.2 packaging increment](AC_CHT_ALPHA2_PACKAGING_20261024.md)
adds the strict public worker method `run_em_network_resistor_cht` and CLI
`em-cosim resistor-cht REQUEST.json`. It executes this same experimental owner;
it does not add thermal feedback or broaden the governing model. The alpha.2
frozen-worker probe runs actual AC/CHT and preserves unsupported states. See
that separate record for package identity and current installer/Linux gates.

Input JSON is capped at 8 MiB after a preflight of depth<=64, <=1 million
traversal nodes, bounded pending work, <=8 MiB aggregate string characters and
<=1024-bit integer tokens. Output is <=16 MiB. These are admission/payload
limits, not a hard resident-memory guarantee. Cancellation is checked before
and between stages, periodically during JSON admission, and by existing child
polls. In-process sparse factorization remains uninterruptible; use external
process supervision for a hard timeout/process-tree stop. No partial coupled
result is published on rejection or cancellation.

The pipeline has no R(T) feedback, buoyancy, turbulence, transient heat, live
SPICE, calibrated EM-body loss, general CAD/PCB domain extraction or MPI.
Supplied S samples may originate from PI, SI or EM analysis, but sampled
passivity does not establish broadband causality, usable GHz board extraction
or measured accuracy. Linux, full-suite, packaged/installer and knowledgeable
human numerical review remain separate qualification requirements.
