<!-- SPDX-License-Identifier: Apache-2.0 -->
# Multi-conductor harness engineering

## Create and inspect wiring

1. Open the project harness editor from the multi-board assembly editor, or
   **Solve > PI > Harness PI** for a standalone harness document.
2. Create connectors and their physical pin identifiers. Add individual wires
   with explicit endpoints. Add splices for branches. The diagram selects each
   connector, splice and wire separately, including parallel wires.
3. In the selection inspector, choose power, return, signal, shield, other or
   unspecified. Assign an explicit return wire where needed. A net label does
   not connect terminals or establish a return path.
4. Select two compatible wires for a differential or twisted pair. Differential
   member order is positive then negative. Specify twist pitch in millimeters
   when known. Members must span the same two connectors, use distinct pins and
   have the same cable assignment. Branches are allowed in the document, but
   the uniform SI analysis excludes branched channels.
5. For an assembly harness, use the pin-map table to change endpoint mappings;
   its shared wiring editor adds conductor metadata to the exact saved map.
   Save boards and links to update the viewport. Independent standalone wiring
   allows arbitrary additional wires and splices.
6. In 3D, routed conductors retain wire identities, role colors and ordered pair
   membership. Picking a wire exposes its identity in the harness inspector.
   Legacy harnesses retain the bundle fallback. Routes terminate at connector
   origins: physical pin offsets are not inferred. Display spacing/radius are
   presentation aids, not manufactured cable dimensions.

The editor preserves vendor extensions, routing and contact metadata. Renaming
or deleting endpoints updates affected references. Assembly metadata that no
longer matches its pin map is rejected before save; repair the map or clear the
incompatible conductor draft deliberately. Existing documents without roles
and pairs remain readable.

## DC power integrity

Use the existing [Harness PI workflow](HARNESS_PI.md). Select **All wires** for
the legacy circuit, or **Explicit selection** to choose power/return wires in
a mixed harness. Supply each included conductor's resistance and explicit
terminal/contact models. Every declared return must be included. Review
selected/excluded wire IDs, currents, voltage drop and I-squared-R loss.

Parallel power and return conductors are separate circuit elements. A wire
color or role does not supply its resistance. Unmodeled excluded signal wires
are not simulated. Harness DC does not solve board copper or distributed fields.

## Signal integrity

In **Harness SI and EM**, select a differential pair or a signal and explicit
return. Supply the complete uniform loop/modal RLGC model, model provenance,
length, reference impedance and frequency sampling. Both conductor lengths
must match the model. The UI starts with empty model fields; it does not guess
electrical parameters from twist pitch or routing.

Run the worker and inspect S21 insertion response and S11 reflection. Stop
cancels this operation and discards late results. Saved SI setup and its returned
result live in `extensions["spike.harness-si"]`. Saving the enclosing project
retains them; reopening displays a matching saved result directly. Editing the
document, selection, model or provenance hides the stale result until rerun.
PI results currently remain session-local; retain CLI output if needed.

This is an **experimental supplied uniform two-port model**. A differential
model must already include both conductors' loop loss and coupling. It does
not extract RLGC, model connector launches, common-mode conversion, crosstalk,
shield transfer impedance or radiation. Twist metadata alone does not establish
those quantities. Full multi-conductor field simulation remains pending.

## Headless interfaces and persistence

Worker operations take exactly `{ "request": ... }`:

| Operation | Request contract | Result contract |
| --- | --- | --- |
| `run_harness_pi` | `spike/harness-pi-request/v1` | `spike/harness-pi-result/v1` |
| `run_harness_si` | `spike/harness-si-request/v1` | `spike/harness-si-result/v1` |
| `prepare_harness_em` | `spike/harness-em-request/v1` | `spike/harness-em-handoff/v1` |
| `run_harness_mtl` | `spike/harness-mtl-request/v1` | `spike/harness-mtl-result/v1` |
| `extract_harness_round_wire_rlgc` | `spike/harness-round-wire-rlgc/v1` | `spike/harness-round-wire-rlgc-result/v1` |

CLI commands are `harness-pi`, `harness-si`, and `harness-em`, each with
`--request request.json` and optional global `--output result.json`. MCP exposes
`spike_run_harness_pi`, `spike_run_harness_si`, and `spike_prepare_harness_em`.
SI is limited to 2049 frequency points and an 8 MiB request. The worker keeps
numerical work off the desktop event loop.
EM preparation rejects before copying if repeated route geometry exceeds
100,000 points or projected output exceeds 16 MiB (`HARNESS_EM_OUTPUT_LIMIT`).
Reduce selected conductors or route detail before requesting the handoff again.

Canonical `spike/harness/v1` wires carry optional `role` and `return_wire_id`.
Top-level `pairs` carry `id`, ordered `wire_ids`, `kind`, optional `twisted` and
`twist_pitch_mm`. Assembly records retain these in
`extensions["spike.harness-conductors"]`, contract
`spike/assembly-harness-conductors/v1`, bound to the exact occurrence connector
IDs and pin map. The assembly adapter preserves complete analysis extensions
and connector contact data. Python validates this binding during project save.

## EM requirements and recovery

**Check EM requirements** retains the selected geometry and returns
`unsupported`; it is not an EM run. Resolve each reported requirement before a
future field adapter can admit it:

| Diagnostic | Resolution |
| --- | --- |
| `HARNESS_EM_SOLVER_UNAVAILABLE` | A harness field solver and geometry translator must be implemented and validated. |
| `HARNESS_EM_EXCITATION_REQUIRED` | Supply reviewed excitation and reference models. |
| `HARNESS_EM_MATERIAL_REQUIRED` | Supply conductor, insulation and shield material models. |
| `HARNESS_EM_BOUNDARY_REQUIRED` | Supply field boundary/environment conditions. |
| `HARNESS_EM_GEOMETRY_REQUIRED` | Retain a valid route for every selected conductor. |
| `HARNESS_EM_SECTION_REQUIRED` | Supply physical conductor cross sections. |

Invalid pairs, returns and stale assembly mappings fail validation rather than
silently changing connectivity. SI rejects a shorted/branched channel or unequal
lengths. Correct the explicit document/model and rerun. No display or successful
DC/SI result establishes EMI qualification.

## Validation basis

Independently authored fixtures check parallel DC current sharing and losses,
plus a matched lossless differential line with L = 1 microhenry/m,
C = 100 picofarad/m and length = 1 m. Its analytical impedance is 100 ohms,
delay is 10 ns, reflections are zero and transmission is exp(-j omega delay).
The SI oracle tolerance is 1e-12 over nine frequencies. Tests also cover
malformed intent, cancellation, worker/CLI/MCP contracts, stale saved results,
bounded 3D sampling, splices, and actual `.spike` save/reopen preservation.
These checks do not constitute measured harness or hardware qualification.

All new implementation and synthetic fixtures are independently authored
SPIKE-owned Apache-2.0 material. No external solver source or dataset was copied.
Numerical human review remains required before release.

## Experimental multi-conductor backend (2026-10-09)

This separate Python backend does not replace the existing DC or uniform SI
adapters. Dedicated worker/MCP methods and heavy-operation bridge entries are
registered separately; the earlier dedicated CLI commands remain unchanged.
This is not an integrated general harness field workflow. No screen/display
offset is used to derive electrical geometry.

`harness_mtl.run_harness_mtl(request, cancel_check=None)` accepts
`spike/harness-mtl-request/v1`; its strict request schema is
`schemas/harness-mtl-request-v1.schema.json`. Supply explicit nodes (including
optional occurrence/terminal/wire identity), one ideal reference node, ports,
segments, contacts, terminations and provenance. Each segment supplies ordered
`wire_ids`, corresponding `from_nodes`/`to_nodes`, length in meters and exact
sampled matrices `r_ohm_per_m`, `l_h_per_m`, `g_s_per_m`, `c_f_per_m` with shape
`[frequency,wire,wire]`. The model's wire order and frequency vector must match
the segment and study exactly. Frequencies increase strictly; DC is supported.

Branch and parallel paths share explicitly named nodes. Contacts are explicit
series R-L models; terminations are explicit parallel G-C models. Zero-R/L
contacts support ideal junctions unless they create a singular system. Every
contact/load requires model provenance. A named reference is an ideal electrical
reference, not an extracted finite return conductor or shield. Ports supply
positive/negative nodes and positive real impedance in ohms. Non-excited ports
are terminated in their reference impedances, as required by S-parameter
measurement; additional loads must be entered explicitly.

Results preserve port/node/segment/wire/occurrence identity and return
`S[frequency,receiver,source]` real/imaginary arrays. Segment terminal voltages
and currents have order `[frequency,wire,incident_port]` for unit incident
power-wave amplitude in sqrt(W); currents point into each segment end. These
are transfer responses, not arbitrary-source operating currents. Optional
`mixed_mode_pairs` partitions all equal-reference ports into ordered +/- pairs;
output order is D1..Dn,C1..Cn with references 2*z0 and z0/2 respectively.
Common/differential conversion and interconductor crosstalk remain in the full
network rather than being discarded into a differential-only subnetwork.

The independently derived state is `[V,50*I]`, satisfying
`dV/dz=-(R+jwL)I` and `dI/dz=-(G+jwC)V`. A matrix exponential relates each
segment's two endpoints. Those relations and KCL form a modified nodal system;
no inverse of an endpoint transfer subblock or modal diagonalization is needed.
Norton port loading yields power-wave S. R/G must be positive semidefinite and
L/C positive definite, all reciprocal and finite. No negative eigenvalue is
clipped, no singular system regularized and no sampled model interpolated.

### Geometry-derived bounded model

`harness_rlgc_geometry.extract_parallel_round_rlgc(request, cancel_check=None)`
accepts `spike/harness-round-wire-rlgc/v1` using
`schemas/harness-round-wire-rlgc-request-v1.schema.json`. It derives a **thin-wire
approximation** for straight solid nonmagnetic round wires above an explicitly
declared ideal infinite grounded plane, in one homogeneous dielectric. Supply
each wire's x coordinate, center height, radius (meters), conductivity (S/m),
relative permeability=1, dielectric permittivity/loss tangent and sweep. Its
returned `model` binds directly to a network segment, including exact wire order.

Independent image potentials give external mutual inductance; homogeneous TEM
duality gives `C=mu0*epsilon*inverse(Lexternal)`. Integrating radial cylindrical
diffusion gives internal impedance
`Zinternal=k*I0(k*a)/(2*pi*a*sigma*I1(k*a))`, `k^2=jw*mu*sigma`.
Scaled Bessel functions and a small-argument series avoid overflow/cancellation;
DC limits are `R=1/(pi*a^2*sigma)` and `Linternal=mu/(8*pi)`.
Dielectric conductance is `w*tan(delta)*C` for the declared sweep.

Admission requires radius/height and radius/center-spacing <=0.05, cross-section
including images <=0.05 dielectric wavelengths and external matrix condition
<=1e8. These are conservative applicability checks, **not a guaranteed accuracy
bound**. Unsupported references, magnetic materials, overlap/slenderness or
electrically large cross-sections return `unsupported` with no usable model.
Individual insulation layers, strands, proximity redistribution, finite/lossy
shields, connector launches, bends, helices and plane losses are not modeled.

### Run and inspect the original example

From the checkout run:

```powershell
.venv/Scripts/python.exe examples/harness/run_multiconductor_reference.py --output-dir build/harness-reference-new
```

Use a fresh directory. The script refuses to overwrite evidence and writes
geometry/network requests and results separately, then prints their SHA-256
digests. The fixture has two explicit 0.2 mm radius wires, 10 mm center spacing,
10 mm plane height, assumed conductivity 5.8e7 S/m, homogeneous er=2.25,
tan(delta)=0.01, one-meter length and DC/1 MHz/10 MHz samples. Four single-ended
50-ohm ports also produce ordered differential/common responses. These are
synthetic inputs, not a measured board or manufactured harness.

The actual run in `build/harness-qualification-20261009` completed with maximum
relative residual 2.75e-16, reciprocity error 5.57e-16 and maximum sampled
singular value <=1. Twelve network tests and twelve geometry tests passed.
Independent oracles cover matched scalar phase/DC, coupled modal phase, KCL
three-port branching, parallel resistor/contact paths and loaded networks.
A noncommuting L/C case agrees with an independently refining lumped pi ladder
at second order. Cylindrical radial-series and exact single-cylinder image
oracles check skin effect and geometric approximation separately. Independent
review identified late-cancellation, boolean nested-sweep and numeric overflow
admission defects; fixes and reproducing regressions now pass, as do unequal
50/75-ohm normalization and explicit reactive-contact/load phase oracles.
The wider focused harness discovery run passed 60 tests using a writable
workspace temporary directory; the sandbox's default temporary path was denied.
The finite-return regression retains a separately modeled 3-ohm return wire
anchored at the reference at one end; it is not silently replaced by an ideal
return. The final example under `build/harness-qualification-20261009-v4`
also retains source/runtime hashes in `evidence.json` and per-segment supplied
model provenance/digests in its result.

Network resource admission limits: 8 MiB request/16 MiB result, 128 nodes,
32 segments, 16 conductors/segment, 32 ports, 257 samples, 256 total unknowns,
100 million `frequency_count*unknown_count^3` work estimate and 131072 complex
response entries. Each dimensionless segment generator has norm <=50; explicitly
subdivide segments that exceed it. Condition >1e12, residual >1e-10, or sampled
passivity/reciprocity violations fail instead of producing an accepted result.
Geometry requests are limited to 128 KiB, 16 wires and 257 samples. Cancellation
polls frequency boundaries and before publication, discarding results; standalone
calls require caller supervision. Dedicated bridge entries use existing heavy
operation supervision; their registration is not installed-GUI qualification.

### Method provenance and remaining qualification

Equations were independently derived; code, prose and synthetic oracles were
independently authored. No external implementation or dataset was copied.
Primary method context: [MIT homogeneous TEM derivation](https://web.mit.edu/6.013_book/www/chapter14/14.2.html),
[MIT thin-wire/image geometry](https://web.mit.edu/6.013_book/www/chapter8/8.6.html),
[MIT magnetic diffusion](https://web.mit.edu/6.013_book/www/chapter10/10.7.html),
[NIST modified-Bessel equations](https://dlmf.nist.gov/10.25) and
[NIST conductor/modal calibration](https://www.nist.gov/publications/calibration-multiconductor-transmission-lines).
These established invariants are not presented as newly invented research.

Sampled passivity/reciprocity do not qualify causality or manufactured cables.
Independent established-solver comparisons, measured correlation, arbitrary
insulated/shielded harness extraction, finite returns, connector full-wave
models, physical twist geometry, PCB coupling, executable near/far fields,
cross-platform release checks and numerical human review remain open.
