<!-- SPDX-License-Identifier: Apache-2.0 -->
# Frozen-frame Cartesian stream presentation, 21 October 2026

Status: bounded visualization implementation with synthetic verification.
Knowledgeable human numerical review before release remains required.
No physical validation or source-solver qualification is claimed.

## Scope and API

`app/src/fieldStreamTracing.ts` exports synchronous
`traceFieldGrid(data: FieldVolumeData, options: FieldViewOptions): FieldStreamline[]`.
It supplies ephemeral polylines and `speed_m_s` samples to the main Three scene.
These paths must remain labelled renderer-generated frozen-frame streamlines.
They are neither solver-returned curves nor transient particle trajectories.
Tube radii are cosmetic; no mass-flow or cross-section interpretation applies.
Other scalar quantities are not interpolated onto generated curves.

Only a declared `complete-cartesian-fluid` volume with at least two unique
coordinates per axis and every Cartesian product entry is admitted, reusing
`cartesianFluidGrid`. Sparse, masked and planar datasets cannot create paths.
No solid shape or fluid gap is inferred. The declaration is trusted input;
unrelated assembly solids do not establish an obstacle-aware interpolation.
Tracing is confined to the convex box of sample centers, not voxel outer faces.

Select a saved frame, a seed axis and density in the field-view controls.
Seeds are the centers of a density-by-density regular subdivision of the
selected axis's middle plane. Forward and backward traces join only at their
own seed, in velocity order. Empty output denotes unsupported input or no
drawable path, not proof that the entire field is zero. Increase display budget,
change the seed plane, or supply original curves if no path appears.

## Reviewed primary sources and independent construction

Reviewed on 2026-10-21; no external implementation source was used.

- Kitware, VTK **7.1** `vtkStreamTracer`, Detailed Description:
  [official reference](https://vtk.org/doc/release/7.1/html/classvtkStreamTracer.html).
  Reviewed normalized-vector arc-length tracing, forward/backward operation,
  fixed Runge-Kutta steps and domain/stagnation/length/step stopping semantics.
  This supplies established visualization context, not a dependency or claim of
  numerical equivalence with VTK.
- NIST DLMF, online section **3.3(i), equation 3.3.1**:
  [Lagrange interpolation](https://dlmf.nist.gov/3.3.E1).
  Reviewed the unique nodal polynomial formula. The tensor product of its
  two-node specialization is independently derived below.
- NIST DLMF, online section **3.7(v), introductory paragraph**:
  [Runge-Kutta methods](https://dlmf.nist.gov/3.7.v).
  Reviewed the truncated-Taylor foundation for first-order ODE integration.
  The page's subsequent RK4 formula is not the implemented method; the
  second-order midpoint construction and error argument below are independent.
  Online DLMF portions are identified by section/equation and retrieval date;
  no unverified release-number claim is made.

For frozen velocity `u(x)` in m/s, a streamline obeys
`dx/ds = u(x)/|u(x)|`, where `s` is geometric arc length.
Let `L` be the largest coordinate span and `o` the minimum XYZ coordinate.
With `q=(x-o)/L`, `sigma=s/L`, we obtain
`dq/dsigma = f(q) = u(o+L*q)/|u(o+L*q)|`.
The same isotropic `L` is used for every component, preserving direction on
anisotropic grids. Coordinates and returned paths remain in the envelope's m
or mm unit. Vector magnitudes remain m/s. This geometric reparameterization
does not require or claim time integration or velocity-unit conversion.

In a containing Cartesian box, set
`t_d=(q_d-a_d)/(b_d-a_d)`. The two endpoint basis functions are
`l_0(t)=1-t`, `l_1(t)=t`, from matching endpoint values with a linear polynomial.
Their tensor products give
`u(q)=sum_(i,j,k in {0,1}) l_i(t_x)*l_j(t_y)*l_k(t_z)*u_ijk`.
Weights sum to one and are nonnegative inside the box. Constant and affine
fields are reproduced exactly in real arithmetic; nonuniform axes are allowed.
This interpolation is only for drawing. It preserves neither discrete flux
conservation nor divergence-free constraints of an originating solver.

For sign `epsilon=+1` or `-1`, explicit midpoint uses
`m=q+epsilon*h*f(q)/2`, `q_next=q+epsilon*h*f(m)`.
Expanding `f(m)=f(q)+epsilon*h*Df(q)*f(q)/2+O(h^2)` gives
`q_next=q+epsilon*h*f(q)+h^2*Df(q)*f(q)/2+O(h^3)`,
matching the trajectory Taylor expansion through degree two. Smooth, nonzero
fields therefore give local order three and global order two on a fixed
interval. Piecewise interpolation derivatives, near-stagnation direction
conditioning and clipping can prevent this smooth-field rate.

All derivation, code, fixtures, analytic oracles and prose were independently
authored for SPIKE. References establish method provenance only; no external
code, examples, figures or data were copied.

## Resource, conditioning and stopping contract

The grid has at most 40,000 centers. Density is clamped to 2..8 (at most 64
paths). The finite segment budget is clamped to 1..16,000; nonfinite budget
falls back to 2,500. Each direction receives
`min(256, floor(budget/(2*density^2)))` steps. Thus total output is at most
16,000 segments and 16,064 vertices, and there are at most 48,000 vector
samples in marching plus 64 seed samples. Each sample uses binary axis searches
and eight vector corners. Grid indexing is bounded by the input cap.

The step is one quarter of the smallest normalized grid interval. Tracing
stops on a stage/endpoint outside the center box, zero/nonfinite speed,
unrepresentable progress, the per-direction step limit, or four normalized
arc-length units. The length check is at step start, so the last step can
overshoot four by less than one step. No extrapolation or boundary projection
occurs; boundary endpoints can fall short by a step. Closed curves can repeat
until capped; no topology or complete streamline coverage is promised.

Inputs with nonfinite coordinate/vector entries or normalized grid spacing
below `1e-12` return no paths. Output is discarded if physical-coordinate
roundoff produces duplicate adjacent points. Isotropic normalization protects
very large/small spans, but cannot recover already-lost coordinate precision.
Velocity normalization near a stagnation point remains ill-conditioned;
fixed steps carry no general trajectory-error tolerance. This bounded
synchronous renderer has no cancellation hook. Future expansion of these
caps requires a responsiveness assessment or worker execution.

## Executed verification

On 2026-10-21, `node app/scripts/test-field-stream-tracing.mjs` passed.
The fixtures are original analytical samples, not measurements:

| Check | Oracle and acceptance | Executed result |
| --- | --- | --- |
| Constant velocity `(2,0,0)` | Straight paths, speed 2 within `1e-13`, domain bounds and traversal | Passed |
| Negative and later-frame vectors | Reversed velocity order; exact selected-frame equivalence | Passed |
| Zero velocity | No paths | Passed |
| Rotation `(-y,x,0)` | Circle of radius `sqrt(1/2)`, analytical angle `s/r` at `s=0.5`; position error below `0.003`, radius error below `0.002` | Errors `0.0006168298194850041`, `0.00015676799539302458` |
| Grid/step refinement 4 to 8 intervals | Affine interpolation exact; half step at identical arc length; error ratio in `3.5..4.5` | `3.9346667534950828` |
| m/mm envelope equivalence | Rescaled positions agree within `1e-12` | Passed |
| Extreme scales | Coordinates `1e-100` and `1e100`, speed `1e100`: finite paths | Passed |
| Rejection and resources | Undeclared/sparse/duplicate/2D/nonfinite/extreme aspect grids; low budget; density and segment caps | Passed |
| Ownership and repeatability | Source unchanged; repeated output identical | Passed |

These checks qualify only the stated presentation behavior. They do not
establish physical prediction, arbitrary-field convergence, obstacle avoidance,
GPU rendering correctness or human numerical release approval.
