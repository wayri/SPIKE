<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent review: presentation-only E/H field lines

Date: 25 October 2026

Status: recommended bounded visualization method; not implemented or executed by
this review. Knowledgeable human numerical review remains required before
release.

## Decision and source boundary

The retained source is
`artifacts/showcase-042-20261025/02-em-fields/fresh-openems-capture/field-samples.json`.
It records an actual openEMS 0.0.36 execution on a Cartesian `23 x 14 x 12`
sample lattice at 0.5, 1.5 and 2.5 GHz, with complex Cartesian E and H samples,
native HDF5 artifact hashes, metre coordinates and the original geometry and
excitation metadata. The requested initial view shall use the 1.5 GHz frame.
Nothing in this method changes, repairs, normalizes or re-solves those samples.

Generate two separately selectable curve families:

- electric-field lines from E, retaining the source declaration `V/m`;
- magnetic-field-intensity lines from H, retaining `A/m`.

Do not label H as B. The fixture is described as `mu_r = 1`, so `B = mu_0 H`
could be a separately declared derived quantity in tesla, but that conversion is
unnecessary for H-line direction and is not part of this recommendation.

The artifact declares `V/m` and `A/m`, while the retained-assembly EM document
describes an unnormalized raw pulse transform as `V s/m` and `A s/m`. Resolve
that metadata inconsistency before presenting quantitative amplitude legends.
It does not affect direction curves under multiplication by one global positive
scale. In every case the display must say **raw, unnormalized Gaussian-pulse DFT**:
it is not a 1 V accepted, 1 W accepted, RMS or calibrated steady-state field.

These curves are renderer-derived frozen-phase field lines. They are not
solver-returned paths, rays, particle trajectories, energy-flow/Poynting lines,
wavefronts, propagation paths, group velocity, causality evidence or validation
of openEMS accuracy. Preserve the source result's `unvalidated` and
`production_qualified: false` states.

## Selected phase and direction equation

For one complex field sample `F(x) = F_R(x) + j F_I(x)` and user phase `phi`,
define only the displayed real projection

`V_phi(x) = Re(F(x) exp(j phi)) = F_R(x) cos(phi) - F_I(x) sin(phi)`.

The initial `phi = 0` view therefore uses the stored real part exactly. For a
nonzero phase control, record the convention as a SPIKE display convention.
The capture does not authenticate the temporal Fourier sign used to interpret
the raw dump as `exp(+j omega t)` rather than its conjugate. Phase zero is
unaffected by that ambiguity. Do not describe nonzero `phi` as physical time
until the openEMS 0.0.36 dump convention is tied to a time-domain oracle.

Where `||V_phi||` is above the declared terminal threshold, an unoriented field
line is the geometric integral curve

`dx/ds = epsilon V_phi(x) / ||V_phi(x)||`, with `epsilon` equal to `+1` or `-1`,

and `s` in metres of geometric arc length. Reversing `epsilon` changes only
curve orientation. Normalization makes geometry independent of field magnitude;
saved magnitudes at curve points retain the original E or H unit. This is not
time integration and `s` is not elapsed time.

## Recommended bounded construction

Prefer an offline VTK-derived curve artifact for this bounded showcase:

1. Verify the exact source file and native HDF5 hashes. Select exactly the
   1.5 GHz E or H complex array and apply the phase projection above without
   changing storage order.
2. Construct `vtkRectilinearGrid` from the retained nonuniform x/y/z axes and
   attach the three-component projected vector at every corresponding sample.
   The capture used openEMS dump mode 2, cell interpolation; do not reinterpret
   these common locations as raw staggered Yee-component locations.
3. Seed deterministic, saved points or bounded seed planes in the actual sample
   box. Retain seed coordinates, field choice, frequency and phase in the
   derived artifact. Seed selection controls coverage and must never be called
   complete field topology.
4. Use `vtkStreamTracer` with `BOTH` directions, normalized arc-length
   integration and fixed RK4. Use physical-length steps bounded by the smallest
   adjacent grid spacing; record the exact initial/minimum/maximum step,
   maximum propagation, maximum steps and terminal magnitude used.
5. Export only finite polylines with sampled source magnitude and explicit
   termination reason. Bind the derived artifact to the unchanged source digest
   and method/version metadata. The viewport may render the saved curves but
   must not export them as solved openEMS field samples.

VTK's official `vtkStreamTracer` documentation states that it integrates
normalized vectors, supports forward/backward/both directions, and terminates
on domain exit, terminal speed, propagation length or step count. It also
distinguishes arc-length steps from virtual integration time:
<https://vtk.org/doc/nightly/html/classvtkStreamTracer.html> (reviewed
2026-10-25). This supplies established method semantics, not evidence that a
particular derived artifact was generated correctly.

The existing SPIKE `traceFieldGrid` implementation and
`docs/validation/FIELD_STREAM_PRESENTATION_20261021.md` provide an acceptable
independent fallback after extracting a geometry-neutral Cartesian-vector
contract. Do **not** mark EM data `complete-cartesian-fluid`; that declaration
has fluid-domain and obstacle assumptions. The existing midpoint method is
second order and already has bounded resource, straight-field and circular-field
tests. Reusing it without a new EM admission boundary would be a semantic error.

## Interpolation, masks and termination

VTK rectilinear interpolation is presentation interpolation between returned
samples. It is not a new Maxwell solution and does not preserve discrete
divergence, curl, flux, conductor boundary conditions or material-interface
jumps. The OpenEMS field-dump documentation states that field components follow
Yee staggering unless an interpolation mode is used; this capture explicitly
records mode 2 cell interpolation. The official format documentation reviewed
on 2026-10-25 is
<https://docs.openems.de/en/latest/concepts/dump_hdf5.html>. It documents current
format semantics, not version equivalence to the executed 0.0.36 runtime.

Apply these fail-closed rules:

- reject a missing frequency, malformed shape/order, nonfinite complex sample,
  nonmonotone axis, hash mismatch or unknown E/H unit;
- stop at the sample-centre domain boundary; never extrapolate;
- stop when projected magnitude is nonfinite or at/below a recorded absolute
  plus relative terminal threshold;
- stop at maximum propagation, step count, integration failure or no
  representable spatial progress;
- do not trace through a region merely because display geometry looks empty;
  without a source-aligned validity/material mask, interpolation remains over
  the complete rectangular sample lattice;
- preserve each forward and backward termination independently;
- do not connect nearby endpoints, snap to conductors or manufacture a closed
  loop. Repeated or nearly returning paths terminate by the ordinary resource
  limits unless an independently tested cycle detector is later specified.

Near nulls the normalized direction is ill-conditioned. Omit or terminate
those traces and expose the omission count. A blank or sparse result means the
chosen seeds/phase/threshold produced no drawable curves; it does not prove a
zero field.

## Required acceptance evidence

Before presenting these curves as native SPIKE evidence, retain deterministic
source-bound tests with predeclared tolerances:

1. **Admission and identity:** exact source/native hashes, 1.5 GHz selection,
   shape `23 x 14 x 12`, C-order mapping and E/H units; corruption must fail.
2. **Phase algebra:** `phi=0` equals the stored real vector bit-for-bit;
   `phi=pi/2` equals negative imaginary and `phi=pi` reverses real under the
   declared `exp(+j phi)` display convention. No peak/RMS conversion occurs.
3. **Constant vector field:** RK4 produces straight collinear paths, constant
   source magnitude, correct forward/backward ordering and domain termination;
   uniform positive rescaling leaves coordinates unchanged.
4. **Circular field:** on the analytical field `(-y,x,0)`, compare position and
   radial drift at a fixed sub-circle arc length, away from the origin. Halving
   the step should show the predeclared RK4 refinement trend. Do not require or
   create a closed endpoint; closure is not an oracle for a bounded open trace.
5. **Null and conditioning:** exact zero, phase-cancelled, nonfinite and
   near-threshold fields terminate without NaNs, duplicate points or arbitrary
   direction. Scaling around the threshold must exercise both outcomes.
6. **Nonuniform axes and storage:** an affine field on nonuniform rectilinear
   axes matches its interpolation oracle; a reordered or malformed flattening
   is rejected rather than silently transposed.
7. **Bounds and resources:** every point remains inside retained sample bounds;
   seed, point, curve, propagation and memory caps are asserted. Repeated runs
   are byte-deterministic where the VTK/runtime build is fixed.
8. **Source nonmutation:** source JSON and HDF5 digests remain unchanged. The
   output declares itself presentation-only and retains field/frequency/phase,
   seed set, integrator, interpolation, thresholds, termination reasons and
   source digests.
9. **Actual-capture sanity:** execute both E and H at phase zero, require finite
   nonempty bounded curves from declared seeds, and inspect that no curve was
   closed or obstacle-clipped by presentation heuristics. This establishes only
   successful visualization of actual samples.

The existing constant and circular tests in
`app/scripts/test-field-stream-tracing.mjs` are useful independent oracles, but
they do not by themselves establish the VTK path, EM admission, phase mapping,
source-grid identity or native renderer acceptance. A native screenshot can
confirm rendering and labels only after the numerical artifact checks pass; it
cannot qualify the field solution.

## Promotion boundary

This method is acceptable for an explicitly labelled showcase of actual sampled
E/H direction at one selected frozen phase. Promotion beyond that scope requires
at least authenticated transform/phase convention, resolved quantitative units,
field/mesh and duration convergence, material-interface treatment, independent
Maxwell comparison and appropriate hardware or measurement correlation. No
visual plausibility, smooth curve or apparent loop closes those gates.

## Executed implementation review, 25 October 2026

The retained execution is accepted for the bounded presentation scope above;
it does not change or validate an EM solver method. This was an independent
structural and numerical-evidence review of `trace_fields.py`, the two emitted
field-line JSON files and `field-line-execution.json`. The tracer was not rerun.

- The source shape is `23 x 14 x 12` (3,864 vectors). The capture's C-order
  flattening is z-fastest. Reshaping to `[x,y,z,component]`, transposing to
  `[z,y,x,component]` and flattening therefore gives VTK's required x-fastest
  point order. The exported grid-cell centres remain in the source C order.
- The six geometry boxes are exactly equal to the supplied
  `3d-electric-field.json` geometry. Geometry remains illustrative context; it
  is not a material or obstacle mask for the unconstrained rectilinear tracer.
- All 7,486 electric and 9,598 magnetic-H vertices are finite and inside the
  retained sample bounds. The line extents are respectively
  `x=[-0.4613984,0.03562569]`, `y=[-6.634659,6.634659]`,
  `z=[-1.077635,6.0999746]` mm and
  `x=[-0.9959807,0.4386003]`, `y=[-10.967785,10.967786]`,
  `z=[-0.7884868,5.5521207]` mm, within source bounds
  `x=[-21.0000016,21.0000016]`, `y=[-11.0000009,11.0000009]`,
  `z=[-2.099999925,6.100000348]` mm. No reviewed curve has coincident endpoints
  at `1e-6` mm; no closure was imposed.
- The retained analytic receipt reports zero constant-field direction drift,
  `2.980232e-9` mm seed-coordinate export rounding, no curves for the zero
  field, and circular-field radial error improving from `2.6851842e-7` to
  `3.4258736e-8` when the step is halved. VTK 9.7.1 emitted float32 points, so
  the coordinates are presentation precision; the `1e-6` mm bounds tolerance
  is still negligible against the 0.3 mm minimum source-axis gap.
- Both quantities produced 50 curves from 25 seeds with forward-and-backward
  tracing. The recorded termination values are limited to ordinary domain and
  propagation-length exits; there is no endpoint joining, solid clipping or
  forced loop construction.
- Recomputed SHA-256 values match the receipt for the source and both outputs.
  The execution receipt must remain coupled to the field JSON files: frequency,
  phase, source digest, seed set and integration settings are structured in the
  receipt rather than fully repeated in each render payload.

For color only, each phase-zero vector field is divided by one positive global
sample-peak magnitude for that quantity. This dimensionless scaling preserves
direction and therefore the normalized streamline geometry. Grid scalar maxima
are exactly one; interpolated line-sample maxima may be lower. Electric and
magnetic-H colors are normalized independently, are not mutually comparable,
and do not represent absolute V/m, A/m, energy, power or RMS amplitude. The
payload's `relative_field` / `relative` label and absence of an absolute legend
are required while the raw pulse-DFT amplitude/unit discrepancy remains open.
The generic `timeS: 0` field is not physical time; the display is the declared
`phi=0` projection at 1.5 GHz.

The remaining presentation limitations are unchanged: interpolation is not
Maxwell-conforming or divergence-preserving, source-aligned material masks are
absent, curves can pass through displayed solids/interfaces, and neither the
actual-capture sanity check nor these plots establishes field-solver
correctness, convergence or quantitative calibration.
