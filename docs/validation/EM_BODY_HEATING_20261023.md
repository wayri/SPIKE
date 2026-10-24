<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied-field volume heating: 23 October 2026

## Method, provenance and applicability

Reviewed foundation: D. Staelin, *Electromagnetics and Applications* (2011),
MIT OCW, section 2.7.2, equations 2.7.13–2.7.31,
[course text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf).
The implementation, derivation, fixtures and prose are independently authored;
no external implementation, demonstration, geometry or test data was copied.
The public EMerge dataset interpolation API was reviewed separately; API
availability is not evidence of physical calibration or field accuracy.

For RMS phasors with exp(+j omega t), the independently derived real inward
power is the negative exterior integral of Re(E cross conjugate(H)). In a
passive isotropic region with absolute permittivity epsilon (F/m), conductivity
sigma (S/m), and dielectric loss tangent, the electric heat density is
q=(sigma+omega*epsilon*tan_delta)*|E|^2 (W/m^3). Conductivity and loss tangent
must describe distinct loss mechanisms; the caller must not count one twice.
There is no peak-phasor factor one-half in this RMS convention.

The raw fields must satisfy inward port flux minus nonport outward flux minus
integrated q = 0 at relative tolerance 1e-8. Only then is a common positive
power scale accepted_port_power/raw_inward_port_power applied to both fields.
Accepted power comes from the existing solved circuit boundary. Each cell's
integrated heat divided by its geometric volume supplies the retained thermal
mesh. Nonport escaping power is not heat. Conduction source conservation must
also pass 1e-8. No normalization can repair a failed raw balance.

The fixed positive Duffy/Gauss rules use 64 volume and 16 face points. They
integrate quadratic polynomial field products on straight tetrahedra; arbitrary
interpolated fields require separate quadrature and Maxwell convergence studies.
There are at most 512 sampling tetrahedra, one exact positive frequency, and
one exterior geometric port. Request/result limits are 8/16 MiB. Magnetic,
surface and PEC heating, internal lumped ports, multiple coherent excitations,
temperature feedback and arbitrary mesh transfers remain unsupported.

## Feedback and regression evidence

Independent review found that old fields could be reused with a changed AC
frequency. The repair binds the captured field packet to frequency, network,
materials, port faces, sampling mesh and solver-run digest. A separate retained
packet digest prevents accidental packet substitution. These are consistency
checks, not cryptographic authentication of a solver. Both
`source_authenticity_verified` and `shared_solver_mesh_verified` remain false:
the sampling mesh is known, but an arbitrary interpolator's underlying FE mesh
is not attested.

Five tests in `tests/python/test_em_body_heating.py` passed. Independently
prescribed lossy Maxwell plane waves at 300 MHz, 1 GHz and 3 GHz satisfy
gamma^2=j*omega*mu*(sigma+j*omega*epsilon). Analytical absorbed power is
P_in*(1-exp(-2*Re(gamma)*length)). An arbitrary common complex field scaling
leaves calibrated heating unchanged. Four thermal refinements (6, 48, 162,
384 tetrahedra) must each exceed L2 slope 1.7. Corrupted volume fields with a
fresh digest must still fail raw Poynting closure. Stale bindings, missing
samples, pre-existing heat and cancellation are rejected.

These are analytical software tests, not an actual EMerge FEM replay,
measurement, material qualification or board validation. Results remain
experimental; knowledgeable human numerical review is still required.
