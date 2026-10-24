<!-- SPDX-License-Identifier: Apache-2.0 -->
# Direct supplied-law nonlinear flux port

This internal reference capability connects the existing stationary nonlinear
P2/domain/Fourier model to the root-owned generic discrete-gradient energy
stepper. It is not an actual H070 material model, a nonlinear lookup table, a
public-route admission or a completed qualified actual-source machine loop.
The independently authored pre-implementation derivation is
[the integration-owner review](PROPULSION_POD_NONLINEAR_PORT_REVIEW_20261024.md).
The author's design, assumptions, primary-source review and bounded milestones
are retained in `output/promo-propulsion-pod-20261023/real_motor/nonlinear-flux-port-design-20261024.md`.

## Mathematics and implementation

Keep the existing non-orthonormal STAR matrix E, phase currents i=Ex, dual flux
q=E^T lambda, and mechanical angle theta. With joint field energy U, unchanged
three winding load columns F, actual gauged tangent K and supplied constant
end-turn inductance Le, solve K Y=FE and K a_theta=-U_a_theta at the converged
field. Thus M=(FE)^T Y+E^T Le E and lambda_theta=F^T a_theta. The latter retains
all three phase derivatives at fixed physical current for controller sensors.
Only the analytic gap depends explicitly on angle in this model. No general
moving geometry or thermomagnetic material dependence is added.

The implementation adds optional `include_sensitivities=False` to the owned
nonlinear motor's evaluate method. Default field evaluation remains unchanged.
Sensitivity CG uses the actual converged tangent and existing exact linear
reference inverse only as preconditioner. Each RHS must pass a true residual
gate `1e-14 + 1e-9*norm(rhs)` in the existing SI residual coordinates. A zero RHS
is permitted. No fixed nonlinear Schur, frozen permeability or dense global
field matrix is introduced.

`DirectNonlinearMagneticPort` has kind `direct-nonlinear-field-port/v1` and
implements flux_coordinates, energy_gradient, energy_difference and
phase_flux_angle_derivative. It solves W_x=q with at most32 damped inverse
Newton iterations and32 backtracks each, inside the actual phase hexagon and
all supplied-law ranges. The objective-decrease check uses a stable difference
of W-q^T x. It rejects a nonpositive/poorly conditioned balanced M, excessive
reciprocity error, unreachable flux, failed range trial or exhausted resource
bound; it never clamps a current or invents a law. The zero-current field is
the declared deterministic initial inverse state; a law not admitting that
state rejects rather than silently choosing another branch. M's admitted
minimum eigenvalue is1e-14 H and maximum condition ratio1e8; these are bounded
reference admission criteria, not proofs of actual winding adequacy.

At finite inverse residual e=q-E^T lambda, the computed Hamiltonian expression
retains H=U+x^T D x/2+x^T e, D=E^T Le E. End-turn storage occurs once. Its
gradients are x and -tau only to the accuracy of the field/inverse solves.
Default field tolerances are1e-11 relative and1e-11 A*m absolute; inverse flux
tolerance is1e-13 Wb-turn+1e-10 norm(q). The original root-owned chain, circuit,
shaft and whole-energy gates remain the acceptance criteria; satisfying only
the inverse or a chain identity cannot qualify field accuracy.

Stable difference methods are added only to the owned nonlinear P2, motor and
modal helper. P2 tensor/PM differences use polarized products at the original
quadrature points. Isotropic energy differences integrate H(b) between endpoint
magnitudes, splitting at supplied knots; small magnitude increments use
deltaB.(2B0+deltaB)/(|B0|+|B1|), with the zero case handled explicitly. Knot
selection follows the traversed side, avoiding double counting a rounded tiny
interval exactly at a knot. Modal differences use stable rotated increments
with cos(delta)-1=-2 sin(delta/2)^2 and polarized positive energies. Joint phase
flux increments come from F^T deltaA. Inverse-residual product differences use
these increments, not subtraction of rounded total phase flux. No PM baseline
is discarded from reported total energy; constants cancel before difference
summation. Piecewise BH joins do not acquire artificial smoothness.

## Resource and identity contract

Per public operation, wall time defaults60s (upper600s), stationary field calls
128 (upper1024), and owned cache array/overhead accounting64MiB (upper256MiB).
Cache entries contain detached read-only state arrays and exact float current/
angle keys; no tolerance rounding or angle snapping. Entries are evicted by
the explicit byte count and basic state size is checked before field allocation.
This counts owned arrays plus a fixed metadata allowance; it is not a native
allocator/whole-process bound. Actual large-domain work still needs an OS job.
The adapter is a synchronous reference object, not a concurrent shared cache.
Inverse calls currently restart from the deterministic zero-current anchor;
cached field states can save exact repeats but do not change acceptance.

Identity binds model constitutive and resource identities, supplied end turns,
port options and exact implementation files. The manifest includes the nonlinear
port, motor, P2 and modal helpers, magnetic_fem, annular_gap, magnetic_p2,
separated_motor and three_phase physics dependencies. Public entry verifies those
dependencies and the STAR duality. Cached states and returned small values do
not expose mutable model state. The field-solve counter resets per operation;
it is not a whole-transient budget. `bounded_run(deadline_monotonic)` supplies
the caller's cooperative whole-run deadline. Nested scopes retain the minimum
deadline; finally restores both enclosing run and operation deadlines after
success or exception. Public operation entry rejects an expired run before
costly dependency validation, and caps its deadline at the run deadline.
Cached states pass the same deadline check. Resource scopes do not modify
constitutive identity. Native operations remain cooperative: an external OS
job is still required to preempt BLAS/native calls at a hard resource limit.
No factor cache across evaluations or table performance shortcut is implemented.

## Executed checks and limits

BLAS1, Python3.12.9, NumPy2.4.2/SciPy1.17.0:43 focused/adjacent tests passed
in16.144s over nonlinear_port, nonlinear_motor, nonlinear_p2, modal_gap,
annular_gap, separated_motor and magnetic_p2; architecture check passed.
The first expanded run had a test passing a NumPy scalar to the existing
strict built-in-angle API; the fixture was corrected to float, preserving the
production guard. No numerical acceptance tolerance was changed.

After integration-owner review, the additional source bindings and run-deadline
scope passed all9 direct-port tests in8.483s. Added tests independently hash the
four previously omitted dependencies, reject a changed binding, prove expired
runs reject before model validation, reject expired cache hits, and check nested
minimum deadlines, per-operation limits, exception restoration and unchanged
constitutive identity. No governing equation or solver tolerance changed.

New discriminating oracles include independent nonlinear re-solves for both
balanced current sensitivity columns and all three angle-flux derivatives;
nonquadratic Legendre round-trip and centered scalar derivative step ladder;
forward/reverse discrete-gradient chain; tiny mixed flux/angle work; exact
invariance of stable differences to an injected1e12 J constant reference;
zero-winding rank rejection; phase imbalance/envelope, unreachable flux,
mutation and resource failures;60-digit Decimal BH-primitive differences
crossing/touching knots; and a separate12-point line integral of the modal
energy gradient for mixed coefficient/angle increments. Existing full-system
linear, PM, quadrature, constitutive and Fourier tests remain passing.

No short compiled-controller supplied-law integration or timestep-refinement
result is claimed in this record yet; that is the integration owner's next
milestone. Actual H070 directional static BH/orientation and PM provenance
remain open. The actual-domain linear-limit diagnostic was deferred before
child launch by its3GiB physical headroom gate; no actual-domain solve occurred.
The earlier generic1007 dense-reference probe passed at323,248,128B whole-child
peak commit and4.35e-16 independent uncondensed residual, but used tiny synthetic
interior factors. It does not establish actual-domain nonlinear admission.

Primary physical foundation actually reopened for this design: Haus and
Melcher, *Electromagnetic Fields and Energy* (1989), official MIT section11.7,
multi-terminal energy/coenergy, reciprocity and torque. The coordinate-gradient
foundation remains the previously recorded review of McLachlan and Quispel,
arXiv1302.4513v1, printedpp2--3, in full-loop review sections1--3. No external
implementation was copied. Numerical-method evidence policy and knowledgeable
human review before release continue to apply.
