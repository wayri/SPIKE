<!-- SPDX-License-Identifier: Apache-2.0 -->

# Experimental enclosure rectilinear refinement and MAC flux transfer

## Scope and status

`python/spike_core/enclosure_refinement.py` supplies a bounded geometry helper
for the [experimental enclosure thermal composition](ENCLOSURE_CHT_3D.md). It inserts selected
cuts into a Cartesian grid and prolongs already computed coarse MAC normal
velocities to those cuts without changing the parent-cell divergence.

This is experimental infrastructure, not a flow solver. It does not locally
refine, rerun, or validate momentum or pressure; generate CAD, octree, boundary
layer, cut-cell, or unstructured meshes; infer materials or solids; or establish
enclosure CFD/CHT accuracy. A composition using it must solve flow on its
declared coarse grid and may use the refined grid only where its separately
documented thermal operator supports it. Every inserted coordinate is a tensor
plane across the complete domain. A narrow three-dimensional request therefore
does not create a local mesh patch.

## API and units

`build_enclosure_grid(grid, *, cancel_check=None)` accepts exactly:

```python
{
    "shape": [nx, ny, nz],                 # coarse cell counts
    "spacing_m": [hx, hy, hz],             # positive metres
    "origin_m": [ox, oy, oz],              # finite metres
    "local_refinement": [{
        "bounds_m": [[x0, x1], [y0, y1], [z0, z1]],
        "split_factor": 2,                 # integer 2 through 4
    }],
}
```

The three coarse counts are integers from 1 through 32 and their product is at
most 4096. Bounds are finite, ordered, nonempty, and contained in the coarse
domain. A coarse interval is selected when its interior overlaps the requested
interval. Each selected interval receives the factor's equal internal cuts.
When regions overlap, their rational cuts are united: factors two and four share
one midpoint, while factors two and three produce cuts at 1/3, 1/2, and 2/3.
Original coarse cuts are never displaced.

The result contains NumPy arrays and is an in-process numerical object, not a
JSON contract:

- `axes_m`, `coarse_axes_m`: three ascending cut-coordinate arrays [m].
- `shape`, `coarse_shape`: fine and coarse `(nx,ny,nz)` cell counts.
- `parent_indices`: three integer arrays mapping each fine interval to its
  containing coarse interval. A coarse cell field is refined by
  `field[np.ix_(*parent_indices)]`.
- `cell_widths_m`, `cell_centers_m`: three one-dimensional arrays [m].
- `cell_volumes_m3`: `(nx,ny,nz)` positive volumes [m3].
- `face_areas_m2`: three MAC-shaped area arrays [m2].

The builder admits at most 64 refinement regions, 64 intervals on any fine axis,
and 8192 fine cells. It computes the mesh counts before allocating
three-dimensional outputs. Physical coarse-coordinate differences must reproduce
the declared spacing to at most `1e-10` relative error. Represented child widths
must meet the same bound against their requested rational fractions of the
declared spacing. Thus a large finite origin that rounds nominal `0.3 m` cells
to alternating `0.25 m` and `0.375 m` cells is rejected rather than silently
giving the coarse flow and refined thermal operators different metrics.
Nonfinite, collapsed, overflowing, or underflowed cuts, centers, face areas, or
cell volumes are also rejected. Cancellation raises `InterruptedError`; invalid
input raises `EnclosureRefinementError`.

`prolong_mac_fluxes(grid, face_velocity_m_s, *, cancel_check=None)` accepts the
unmodified built-grid result and coarse normal-velocity arrays with shapes
`(nx+1,ny,nz)`, `(nx,ny+1,nz)`, and `(nx,ny,nz+1)`. Integer and floating arrays
are accepted and converted to double precision; Boolean, complex, malformed,
or nonfinite arrays are rejected. It returns refined arrays under
`face_velocity_m_s` and measured diagnostics. It never constructs a velocity by
averaging cell-centered samples.

## Independently authored reconstruction and invariants

Consider one coarse rectangular cell with width `H_d` in direction `d` and its
two stored normal face velocities `U_d^-` and `U_d^+`. Within that cell the
implemented reconstruction is

```text
theta_d = (x_d - x_d^-)/H_d
u_d(x) = (1-theta_d) U_d^- + theta_d U_d^+ .
```

Each component is affine only in its own coordinate and constant over the two
tangential coordinates of that coarse face patch. This is the rectangular
lowest-order Raviart-Thomas form used here for transfer, not a new mixed finite
element solve. At every retained coarse plane, the original coarse face value
is copied directly, so adjacent cells share one normal value and an exactly zero
coarse wall-normal face remains exactly zero on all its fine subfaces.

For any fine cell wholly contained in its parent coarse cell,

```text
div_h(u_fine) = sum_d (U_d^+ - U_d^-)/H_d = div_H(u_coarse).
```

The identity holds even when the coarse divergence is nonzero. It transfers the
input divergence; it does not project a defective field to incompressibility.
Likewise, on one coarse face patch the normal value is tangentially constant and
the fine areas partition the coarse area, so

```text
sum_subfaces u_f A_f = U_H sum_subfaces A_f = U_H A_H.
```

Diagnostics calculate rather than assume both identities. They report maximum
coarse and fine divergence, maximum parent/fine divergence difference, a
component-gradient divergence scale and relative difference. Coarse-face flux
diagnostics report the aggregate absolute integrated error [m3/s], maximum patch
error [m3/s], an absolute integrated-flux scale [m3/s], and relative error.
They also count exactly-zero coarse patches and measure their maximum refined
velocity error. Absolute aggregation avoids hiding individual errors behind
opposite-sign flux cancellation.

The transfer is exact for this discrete space up to floating-point arithmetic.
It does not improve the spatial accuracy of the coarse flow, represent
tangential variation inside a coarse face patch, or preserve moments beyond the
normal face integral. Highly separated coordinate or velocity scales can be
rejected when required arithmetic is not finite. Low diagnostic residuals prove
only these transfer invariants, not physical model accuracy or convergence.

## Reviewed foundations and clean-room record

The following sources were reviewed on 20 October 2026. No external source code,
test data, mesh, prose, or implementation was copied or adapted.

- NIST, FiPy 4.0.3, [Finite Volume Method](https://pages.nist.gov/fipy/en/stable/numerical/discret.html),
  last updated 18 June 2026: the mesh and cell-centered finite-volume discussion
  and convection equation (2), where a control-volume divergence becomes a sum
  of normal face values times face areas. This supports the face-integral
  conservation observable; FiPy implementation code was not inspected.
- P.-A. Raviart and J.-M. Thomas, *A mixed finite element method for 2-nd order
  elliptic problems*, Lecture Notes in Mathematics 606 (1977), pp. 292-315,
  [DOI 10.1007/BFb0064470](https://doi.org/10.1007/BFb0064470): the Springer
  publisher record and its two-page preview, printed pp. 292-293, were reviewed.
  Those pages state the equilibrium equation `div(q)+f=0`, the mixed-method
  purpose, and that section 5 treats rectangular elements. The unavailable
  chapter body was not treated as reviewed evidence for the formula above;
  the rectangular interpolation and its conservation proof were derived
  independently in SPIKE notation.

## Executable verification and remaining gates

`tests/python/test_enclosure_refinement.py` provides independent checks for
nonzero origins, anisotropic widths, narrow-region interval selection, tensor
plane propagation, overlapping rational factors, retained coarse cuts, axis
ordering, exact material-parent mapping, volume partition, and all resource and
finite-geometry controls. A three-dimensional manufactured field
`u=x+0.2`, `v=2y-0.7`, `w=-3z+1.1` independently checks the interpolated field,
zero divergence, parent divergence equality, and integrated face fluxes.
Separate cases cover nonzero divergence, exact zero-wall preservation, large
cancelling gradients, malformed fields, and cancellation.

Run the focused evidence with:

```powershell
.venv-emerge3\Scripts\python.exe -m unittest tests.python.test_enclosure_refinement -v
```

These helper tests are mathematical and software verification only. The
separate [CHT evidence](validation/ENCLOSURE_CHT_METHOD_20261020.md) records actual
composition runs and bounded flow/conduction/time-refinement checks; it does
not establish local momentum refinement, general enclosure accuracy,
external-solver/measured validation or human numerical release review.
