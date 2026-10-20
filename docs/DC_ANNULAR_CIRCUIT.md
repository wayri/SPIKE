<!-- SPDX-License-Identifier: Apache-2.0 -->
# Explicit source annuli and coupled land/barrel DC ports

This bounded extension targets one explicit coaxial stack with annular lands,
uniform annular face-current patches and fresh gap barrels. It must not infer
an electrode from a drill-center point, turn arbitrary pads into circles, weld
attachment labels, reuse imposed helper currents, or claim full PI01-S02.

## Frozen acceptance and governing derivation

Before implementation: check annular axial and radial analytical resistance,
independent quadrature/field heat and conservative face flux. For the coupled
network, compare explicit resistor-network MNA, analytical series limits, current
and conductivity scaling, direction/order changes, zero drive, reciprocity and
passivity. Source/geometry identity and unsupported shape cases must fail closed.
All-body KCL, per-edge KVL and source work versus separately owned land/barrel/
resistor heat must pass 1e-8 relative to their physical operand scales. Retain
raw residuals and actual final land fields. Never adjust supplied currents,
symmetrize/project a response or change existing board thresholds to pass.

Reviewed 2026-10-21: Haus and Melcher, MIT online *Electromagnetic Fields and
Energy*, [7.2](https://web.mit.edu/6.013_book/www/chapter7/7.2.html), steady
conservation, Ohm/insulating-boundary/conductance discussion; and
[7.4](https://web.mit.edu/6.013_book/www/chapter7/7.4.html), source-free linear
superposition, conductance matrices and uniqueness. Embedded equation images
were not separately transcribed. The following current-driven reduction,
coupled equations, code, fixtures and test oracles are independently authored.
No external implementation or dataset is incorporated. Annular field mathematics
and quadrature are recorded separately in `DC_ANNULAR_LAND.md`.

Let each body's independent finite patches have inward currents I with sum I=0.
Choose its last patch as reference and solve each unit current pair to obtain
the reduced resistance Zred mapping nonreference currents to potential
differences. These patches are distributed Neumann contacts, not equipotential
electrodes. Embed Zred as the upper-left block of Z, with zero reference row/
column, so U=Z*I+G*g, where G maps ports to body gauge potentials g.
Require finite reciprocal positive reduced responses; retain their actual
coefficients without a numerical passivity repair.

For each explicit directed barrel or resistor, let A have +1 at its source
port and -1 at its target. With prescribed external inward source currents s,
edge currents j satisfy I=s-A*j and A^T*U=R*j. Therefore

```
H = R + A^T*Z*A
H*j - A^T*Gfree*g = A^T*Z*s
-Gfree^T*A*j = -Gfree^T*s
```

One body gauge is zero. Global sum(s)=0 and connectivity are required; recover
KCL on every body, including the removed redundant equation. Scale H by a
representative positive edge resistance and solve for g/Rscale to keep units
consistent. Screen condition and backward residual, then physical KCL/KVL.
There is no explicit matrix inverse, regularization or current clipping.

Energy follows directly: s^T*U=I^T*U+j^T*R*j. Final land fields must be freshly
solved with I, matched to reduced voltage differences and retained by source
identity. Sum actual land Joule W, fresh physical barrel I^2R W, and explicit
resistor I^2R W separately. No mean energy J or thermal association is inferred.
Barrel R and owned volume come from the explicit face-to-face annular gap,
not an old center span. Source/target patches must match its radius and slab
face exactly. Different semantic labels do not define electrical connections.

The strongest compact network oracle independently assembles ordinary resistor
stars. A body with port resistors r_i has reduced matrix
`diag(r_nonref)+r_ref*ones`. Connected stars and known edge resistors can be
solved using ordinary nodal analysis without the reduction above. Full annular
axial series cases independently test the field/circuit composition.

## Source and validity boundary

Only an explicitly selected supported circular, centered circular-drill plated
pad may supply annular geometry. Preserve its source file hash, normalized
record, source ID, net, layer and center. Slab faces, conductivity, plating and
electrode intervals remain explicit modeling inputs. A pad is not automatically
a terminal. Noncircular/offset/unknown-plating cases reject. Source mapping does
not import arbitrary board surroundings or specify the original EBrake electrode.
All runtime results remain experimental with production and complete-board
qualification false. Required human numerical release review remains separate.

## API, execution and resources

`dc_annular_stack.solve_annular_stack` consumes the strict
`spike/dc-annular-stack-request/v1` request. It contains explicit axial
`ownership`, `lands` (land ID, annular request, optional source binding), one
`connections` record per gap, optional positive `resistors` with explicit
land/contact endpoints, and complete per-patch `external_currents` maps.
Master patch currents must be zero; actual currents come from the coupled
solve. Source ownership helper currents remain historical inputs and never
supply solved barrel fields. Final gap geometry excludes those imposed-current
diagnostics. Actual signed barrel current density is A/m2 and owned gap volume
is m3; all losses are W, including separately retained mean W/m3.

`dc_annular_source.bind_annular_pad_source` authenticates one exact source pad;
`solve_source_annular_stack` revalidates every native binding before and after
the solve. The pure solver checks binding digest/geometry only and explicitly
reports that distinction. Native import proof is supplied by the importer-owned
`kicad_source_evidence` adapter. Offset drills and unsupported layer-removal or
padstack geometry reject rather than treating omitted normalized fields as zero.

The existing reference stack is bounded to2..8 lands, each2..8 patches and512
cells, a total cell-times-patch work budget8192, up to16 supplied resistors,
32 total circuit edges and2 MiB serialized request. Unit field results are
retained with the final fields. The circuit condition budget is1e10; individual
response positivity/reciprocity is screened without repair. Cancellation is
checked between bounded field solves, not within a factorization. Dense small
port systems and sparse per-land solves are research references, not accelerated
production kernels. NumPy/SciPy binary versions must accompany execution evidence.

Run the original supplied example using the environment with NumPy/SciPy:

```powershell
python examples/dc_annular_stack/run_stack.py examples/dc_annular_stack/three-land.request.json build/annular-result.json
```

For a request containing authenticated native pad bindings add
`--authenticate-sources`. A native pad supplies dimensions and identity; the
caller must still supply the electrode support, slab faces and material. The
retained-result validator independently integrates physical fields with32-point
quadrature and checks local weak law, full flux recovery, every response column,
actual coupled KCL/KVL, geometry and separately owned heat without a second solve.
This certifies the bounded discrete model, not the continuum approximation of
uniform interface flux or pointwise interface potential continuity.
