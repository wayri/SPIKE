<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent supplied multiport fixture-removal oracle

Date: 2026-10-24. This record and its test oracle were independently authored
by the review agent, separately from the production implementation author.
Scope is offline sampled linear network algebra; it does not establish
calibration, measurement uncertainty, source causality, broadband passivity,
SI08 family completion, or release qualification.

## Primary mathematical foundation and assumptions

Reviewed primary source: Roger B. Marks and Dylan F. Williams, *A General
Waveguide Circuit Theory*, J. Res. NIST **97**, 533 (1992), section 3.4
(scattering representation, page 547) and section 5 (power waves, page 555),
[NIST archival article](https://nistdigitalarchives.contentdm.oclc.org/digital/api/collection/p16009coll6/id/74796/download).
The reviewed invariants are the linear relation between incident and outgoing
waves and the real-reference wave-power difference. This source supplies those
foundations, not the numerical recovery algorithm or test fixtures below.
Only the paper was consulted; no external implementation was examined.

All connected ports share one positive real reference resistance in ohms.
Frequency samples are in hertz; scattering coefficients and conditioning
metrics are dimensionless. Wave amplitudes have square-root-watt normalization.
Connections identify opposing incident/outgoing waves at the same declared
reference plane. Active and nonreciprocal networks are allowed. Supplied real
DC matrices are algebraic endpoint data: the paper's waveguide-field analysis
excludes zero frequency and is not evidence for a physical DC extrapolation.
No physical model between supplied frequencies is inferred.

## Independently assembled connection system

Let F be the supplied 2N-port fixture, partitioned into exterior E and
interior I ports, and let D be the N-port DUT. At one frequency choose an
arbitrary exterior incident vector u. Unknown outgoing vectors are x=bE,
y=bI, z=bD. Ideal reference-plane connections impose aI=z and aD=y.
The three independent constitutive equations are

```text
x - F_EI z = F_EE u
y - F_II z = F_IE u
z - D y    = 0
```

The oracle assembles and solves the entire 3N by 3N block system

```text
[ I   0   -F_EI ] [x]   [F_EE]
[ 0   I   -F_II ] [y] = [F_IE] u.
[ 0  -D     I   ] [z]   [  0 ]
```

Taking u=I obtains every column of the measured exterior scattering matrix
from x. The original D is the independent expected recovery result. The oracle
does not call production removal or its helpers, invert transmission blocks,
or reproduce its DUT-recovery expression. It separately checks the complete
connection residual to absolute/relative tolerance 2e-13.

Fixture storage is then permuted, with names retaining physical identity.
This tests indexing independently of the block-system arrangement. A second
test changes only requested DUT ordering and checks covariant row/column
permutation of the output.

## Conditioning review and adversarial cases

Both fixture transmission blocks must have full rank for this production
recovery representation; DUT transmission need not. Zero DUT matrices and
purely reflecting diagonal DUTs therefore remain admissible. The tests reject
singular fixture transmission, smallest transmission singular value below
1e-12, individual condition above 1e8, and a product above 1e8 even when each
individual condition is below that limit. These are numerical admission
screens, not calibrated measurement dynamic-range claims.

A contradictory supplied measured matrix M=-I with F_EE=0 and
F_EI=F_IE=F_II=I gives singular recovery and must fail. Reconnection also
requires its own check: take D=diag(0,0.5) and
F_II=[[0,1e6],[0,0]], with identity transmission and zero exterior reflection.
Here D F_II=0, so recovery is well conditioned, while I-F_II D has an
off-diagonal entry -5e5 and condition approximately 2.5e11. The implementation
correctly rejects this separate nonnormal feedback hazard.

Backward residuals and reconnection agreement do not bound forward error
uniformly over all admitted matrices. The test recovery tolerance of absolute
2e-12 plus relative 2e-12 is fixture-specific. There is no discretization or
iterative convergence parameter in the algebraic inversion. Independently
computed exact-network fixtures and residuals are the applicable checks;
frequency/measurement convergence remains outside this test's claim.

## Executable acceptance and findings

Owned test: `tests/python/test_sparameter_multiport_deembedding.py`.

- Dense complex nonreciprocal fixture reflections/cross-coupling and active
  DUTs for N=1,2,3,4,8; matching real DC cases and arbitrary fixture storage.
- Nonuniform frequency sweep, independently generated phase variation and
  explicit DUT-map permutation; no causality claim from that sweep.
- Zero DUT transmission, matched DUT, pure reflection and retained active gain.
- Singular/weak/ill-conditioned transmission, condition-product, recovery
  and nonnormal reconnection rejection, with exact structured error codes.
- Invalid IDs, maps, reference, grid, finite/DC data and fields; port/sample
  resource limits; immediate/late cancellation and failing callbacks.
- Input immutability and retained source snapshots/status/physical names.

Initial command `python -m unittest tests.python.test_sparameter_multiport_deembedding -v`
ran six tests in 0.342 s, with one failure: `frequencies_hz=null` reached the
output-size preflight's `len()` and was misclassified as numerical failure.
The finding was sent to the production owner; tests retain the requirement
for `MULTIPORT_DEEMBEDDING_INVALID_REQUEST` rather than weakening acceptance.
After the owner correction and added frequency/map coverage, the same command
passed all seven tests with zero skips in 0.337 s. No full suite, measured
fixture or human release review is implied by focused tests.

## Clean-room statement

Equations, fixture numbers, oracle construction, tests and prose are original
SPIKE work. Mathematical reference attribution does not supply third-party
code, data, implementation rights or measurement evidence.
