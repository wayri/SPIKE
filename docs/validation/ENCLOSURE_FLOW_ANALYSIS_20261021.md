<!-- SPDX-License-Identifier: Apache-2.0 -->

# Experimental supplied-field probes and streamlines

## Claim, ownership, and exclusions

`python/spike_core/enclosure_flow_analysis.py` reconstructs a supplied, steady,
stationary-frame shared MAC face field on an admitted rectilinear enclosure
grid. It evaluates physical point probes and bounded forward streamlines.
This is not a new flow solver, a momentum-residual check, a physical experiment,
or proof of predictive accuracy. A mass-conserving fabricated field can pass
admission. Results therefore identify `source_data_kind` as
`supplied_shared_face_field`, `model_status` as `experimental`, and
`production_qualified` as false.

The implementation is private in-process Python. It adds no worker route,
public capability, result schema, UI, screenshot, CAD interpretation, pressure
or temperature interpolation. It admits only closed stationary fields;
external flows, inflow/outflow boundaries, time-varying data, rotating-frame
velocity, moving geometry, blades, and particle inertia are unsupported.
It cannot derive meaningful transverse gradients, vorticity, or Q criterion
from this reconstruction: the local velocity Jacobian is diagonal and
tangential traces can jump at cell boundaries.

## API and source identity

Call `analyze_enclosure_flow(request, cancel_check=None)` with exactly:

```python
{
    "contract": "spike/enclosure-flow-analysis/v1",
    "grid": built_grid,             # build_enclosure_grid result, not JSON
    "fluid_mask": boolean_array,    # fine-grid cell shape
    "face_velocity_m_s": [ux, uy, uz],  # shared fine-grid MAC arrays
    "velocity_reference_frame": "stationary",
    "probes_m": [[x, y, z], ...],
    "seed_points_m": [[x, y, z], ...],
    "controls": {
        "max_time_s": 1.0,
        "max_step_s": 0.05,
        "max_points_per_streamline": 512,
        "max_cell_events": 256,
        "max_total_points": 4096,
        "max_output_bytes": 2000000,
        "max_runtime_s": 10.0,
    },
}
```

Controls may be omitted individually, using the defaults above; unknown
controls and top-level keys are rejected. Input arrays are not mutated.
After validation, the working axes, mask, and velocities are copied.
Cancellation is checked before work and during admission, probing, and tracing.
This is an in-process API, so concurrent mutation of the input during admission
and arbitrary slow/custom Python objects or cancellation callbacks are outside
its contract.

The result contract is `spike/enclosure-flow-analysis-result/v1`. Completed
output includes probes, streamlines, a SHA-256 source digest, mass-admission
diagnostics and explicit limitations. The digest binds ordered axes, mask,
normal velocities, normalized requested locations, frame, and effective
controls, with shapes and canonical little-endian float64/Boolean bytes.
It identifies supplied data and analysis options, not an authenticated solver
run or code revision. Source-code binding is the responsibility of the caller's
run ledger.

Probe and trace point records carry `position_m`, `velocity_m_s`, `speed_m_s`,
and `cell_index`. Trace points additionally represent elapsed tracking
`time_s` and cumulative `arclength_m`; probe records carry zero for these two
fields and additionally contain `divergence_s_inv`. Tracking time is the
parameter in `dx/dt=u_h`; it is not a transient CFD solve time step.

All requested coordinates must be strictly inside the outer domain. A probe
exactly on an internal plane uses the higher-index cell (and is rejected if
that cell is solid). Its normal trace is unique, but its tangential trace
generally is not. Seeds must be strictly inside one fluid cell, off every grid
plane. There is no automatic seed movement, obstacle inference, or epsilon
nudge. A trace endpoint on an exit face reports the upstream cell and
upstream velocity: its `cell_index` owns the preceding path segment.

## Independently authored reconstruction

For a cell with lower coordinate `l_d`, upper coordinate `r_d`, width
`h_d=r_d-l_d`, volume `V=h_x*h_y*h_z`, and normal velocities `U_d^-`, `U_d^+`,
define

```text
theta_d = (x_d-l_d)/h_d
u_d(x) = (1-theta_d)*U_d^- + theta_d*U_d^+
b_d = (U_d^+-U_d^-)/h_d .
```

Each component depends only on its own coordinate. This is the rectangular
lowest-order Raviart-Thomas (RT0) form already derived for SPIKE's
[refinement transfer](../ENCLOSURE_REFINEMENT.md); it is not trilinear
interpolation of cell-centered vectors.

The two traces on a shared face have exactly the same normal component
because they use the same stored face unknown. On each cell,

```text
div(u_h) = b_x+b_y+b_z
V*div(u_h) = sum_d A_d*(U_d^+-U_d^-)
integral_cell u_d dV = V*(U_d^-+U_d^+)/2 .
```

The first identity transfers the supplied finite-volume divergence everywhere
inside the cell. The second is the closed-volume normal-flux balance and
holds on nonuniform cells using their physical areas. The third specifies
volume-weighted integrals, not an unweighted average across unequal cells.
Constant and diagonal-affine vector fields are represented exactly within a
cell. Smooth fields with transverse variation are not generally represented
exactly; no higher-order spatial accuracy is claimed.

At a solid or exterior face, the input normal velocity is required to be
exactly zero. Interpolation therefore preserves impermeability. It does not
preserve tangential no-slip at that wall, since the tangential RT0 components
are constant in the wall-normal coordinate. Tangential discontinuity and this
wall limitation are emitted in every result.

## Independently authored cell-exact tracking

Within one fixed cell, start at `x0` with reconstructed velocity `v0`. The
separable initial-value problem is

```text
dx_d/dt = v0_d + b_d*(x_d-x0_d)
u_d(t) = v0_d*exp(b_d*t)
x_d(t) = x0_d + v0_d*t*phi1(b_d*t)
phi1(z) = expm1(z)/z, with phi1(0)=1 .
```

Differentiating the last expression recovers the initial-value problem and
initial position. `expm1` avoids subtracting two nearly equal exponentials;
the `v0*t*phi1` form avoids the separately large ratio `v0/b`.
There is no ODE truncation error inside a cell apart from floating-point
arithmetic. Sampling more points does not improve the underlying field.

The sign of a nonzero velocity component is constant along this local
trajectory. Choose its candidate exit face in that sign's direction. If the
face velocity is zero or of opposite sign, that face is unreachable in finite
time: the trajectory approaches or cannot cross the affine equilibrium.
Otherwise, candidate travel time is

```text
t_exit = distance/v0                         if b=0
t_exit = log(u_face/v0)/b                    otherwise .
```

For nearby same-sign velocities the implementation uses
`(distance/v0)*log1p(r)/r`, `r=(u_face-v0)/v0`, with the limit one at `r=0`.
For widely separated magnitudes it uses the difference of logarithms to avoid
overflowing a ratio. Nonpositive or nonfinite candidate times are rejected.
The earliest candidate face event limits the advancement. Each interval also
obeys `max_step_s`, the remaining time horizon, and `max_d |b_d*dt| <= 0.5`.
The latter limits exponential and quadrature dynamic range; it is not a CFD
stability criterion.

Only the recorded exit coordinate is set to its exact grid plane.
Near-simultaneous exits, within `64*epsilon*t_exit`, stop as
`ambiguous_cell_edge` rather than guessing a diagonal route through multiple
cells. This event tie convention has roundoff-scale positional uncertainty.
After an unambiguous event the direct neighboring cell must be fluid. No
nonadjacent lookup, cell skipping, or position nudge is used. A componentwise
monotone exact local curve and the straight display chord between its
endpoints lie in the same convex cell. The code checks both endpoint
containment and accidental rounded contact with non-exit boundaries. Such
contact stops at the previous accepted point as `precision_limit`.

For an admitted closed field, solid and exterior normal flux is zero, so a
finite-time path should not cross those faces. Defensive termination reasons
`solid_boundary` and `domain_boundary` remain present, but the tests do not
claim they are normally reachable under this contract. Exact stagnation,
finite time horizon, per-trace point/event caps, ambiguous corners and loss of
representable progress are explicit stop reasons. `status=completed` means
the reconstruction returned these bounded traces, not that every requested
tracking horizon was reached. Global cancellation or resource/numerical
failure returns no probes or streamlines.

## Arclength and precision policy

Each accepted interval estimates
`integral_0^dt sqrt(sum_d(v0_d*exp(b_d*t))^2) dt`.
The implementation uses scale-safe `hypot` and separate 8- and 16-node
Gauss-Legendre quadratures. It accepts an interval only when their difference
is at most `1e-10` times the 16-node integral. Cumulative arclength uses the
16-node values, while the sum of the absolute differences is reported as
`arclength_quadrature_error_estimate_m`. This is an error estimate, not a
rigorous bound and not a geometry/field-model uncertainty estimate.

Arithmetic runs with NumPy overflow, underflow, division and invalid-operation
traps. Shape, numeric type, finiteness, grid metrics, retained coarse cuts and
representable cell interiors are checked before tracing. The complete field
must satisfy

```text
max_fluid |div_h u| <= 1e-9 * max_faces |U| / min_cell_width .
```

There is no dimensioned nonzero-velocity floor: exact zero passes as zero;
unrepresentable velocity/gradient/tolerance scales are rejected rather than
silently becoming zero. This is an inherited discrete mass budget, not a
momentum convergence or physical-flow test. Output is finite JSON-compatible
data; normalized source-coordinate types are included in the digest.

## Bounded resources

The existing grid helper limits remain: 8192 fine cells, 64 intervals per
axis, and 4096 coarse cells. This helper accepts only that built geometry;
it does not construct octrees, cut cells, or boundary layers.

Hard request limits are 64 probes and 16 seeds; 2-1024 points per streamline;
1-1024 cell events per streamline; 1-8192 aggregate probe/trace points;
1024-2,000,000 output bytes; positive tracking horizon at most 1e6 seconds;
positive sampling interval at most 1e3 seconds; positive wall-clock budget at
most 30 seconds. Grid and field storage is O(number of cells/faces), with no
global solve or dense operator. Point storage is bounded by aggregate count.

Per-point serialized bytes are counted during construction; the full compact
ASCII JSON encoding is checked before completion. Thus metadata cannot evade
the final byte cap. Failed admission, overflow/underflow, aggregate point
budget, output bytes, or runtime budget produces `blocked`, without partial
fields. Cancellation produces `cancelled`, without partial fields. Per-trace
caps instead produce an explicitly terminated valid prefix. Runtime checking
is cooperative, not an operating-system hard deadline.

## Reviewed primary foundations and clean-room record

Reviewed on 21 October 2026:

- D. W. Pollock, *Semianalytical computation of path lines for finite-difference
  models*, Ground Water 26(6), 1988, 743-750,
  [DOI 10.1111/j.1745-6584.1988.tb00425.x](https://doi.org/10.1111/j.1745-6584.1988.tb00425.x).
  The scanned primary article's printed pages 744-746, Theory, equations
  (3)-(14), were visually inspected from the
  [university-hosted article scan](https://gradst.unist.hr/Portals/9/docs/katedre/Privredna%20hidrotehnika/DSG%20Modeliranje%20toka/Pollock_1988.pdf).
  These cover normal-component linear interpolation, cellwise mass balance,
  separable exponential paths and travel-time events. The groundwater/Darcy
  constitutive model, porosity model and example datasets are not implemented.
- The exact reviewed Raviart-Thomas 1977 preview and NIST finite-volume
  reference scopes are retained in
  [the existing reconstruction ledger](../ENCLOSURE_REFINEMENT.md).
  The unavailable Raviart-Thomas chapter body is not represented as reviewed.

The stable formula choices, boundary tie policy, resource contract, code,
fixtures, derivation and tests above are independently authored. No external
implementation, prose, test data, figures, or mesh was copied or adapted.
The PDF skill was used only to render and inspect the scanned equations,
not to create an output artifact or import a third-party implementation.

## Executed verification

On 21 October 2026, using `.venv-emerge3/Scripts/python.exe`:

```powershell
.venv-emerge3/Scripts/python.exe -m unittest tests.python.test_enclosure_flow_analysis -v
.venv-emerge3/Scripts/python.exe scripts/check_architecture.py
```

All 13 focused tests passed in 0.046 s; the architecture guard passed.
The subsequent [integrating benchmark](CFD_CAPABILITY_INCREMENT_20261021.md)
adds a fourteenth native/JSON replay-equivalence check and verifies composition
with actual accepted coupled-research face fields. That later record owns the
current source-bound receipt identities.
Fixtures independently construct closed divergence-free fields from discrete
streamfunction differences, including genuinely nonuniform cells. They do not
call a momentum solver to create their expected answers.

The affine two-dimensional fixture has `u=(4x,-4y,0)` in the tested cell and
seed `(0.25,0.25,0.3)`. Its independent analytical curve is
`(0.25*exp(4t),0.25*exp(-4t),0.3)`. At the six samples through `t=0.1 s`,
the measured maximum position error was zero at printed double precision.
Computed arclength was `0.1488586320460899 m`; the discrepancy against an
independent adaptive quadrature of the analytical speed was zero at printed
double precision, with reported 8/16 Gauss estimate `1.734723475976807e-17 m`.
These observations are fixture-specific, not general roundoff guarantees.

A longer run with `max_step_s=1` records its first exit at `log(2)/4 s`,
position `(0.5,0.125,0.3)`, and advances through three cell events with eleven
points before its `1 s` time limit. Every recorded segment is independently
checked inside its stated fluid cell. A separate all-three-component
manufactured curl has `u=(4x,4y,-8z)` in the tested cell; its three exponential
coordinates pass a `3e-15` relative position tolerance.

Other assertions cover constant-field trajectories under sampling refinement;
normal continuity, volume-weighted integral and flux identities on unequal
cells; obstacle impermeability, tangency and disconnected stagnant regions;
simultaneous-corner stopping; exact-zero fields; deterministic digests and
NumPy scalar normalization; no input mutation; grid/field/seed/option forgery;
nonfinite and underflow cases; cancellation after partial internal work;
timeout, aggregate point and byte caps; and no qualified-physics output claim.

Only the focused suite and architecture check above were executed for this
owned slice. Repository-wide and composed solver execution is owned by the
parent integration task. No new measured/external CFD validation, general
streamline spatial convergence claim, wall-boundary-layer qualification, or
human numerical release approval is established. Knowledgeable human review
remains required before release.
