# ADR 0115: bounded native CHT and supplied surface exchange

Date: 2026-10-20. Status: accepted for experimental development, not release
qualification. New broad CFD development is explicitly owner-authorized.

## Decision

Extend the owned MAC cavity with a separate C++ steady conjugate-energy
executable, retaining the original executable's JSON and scope. Reuse actual
accepted staggered faces, a shared conservative thermal operator and existing
OS-supervised process execution. Python owns SI admission, independent result
checks and worker/CLI orchestration. There is no new dependency or language.

Expose `spike/native-cht-request/v1` and result/v1 through `run_native_cht`.
The domain remains a square fluid between two quarter-height solid slabs;
supplied constant material properties do not imply general fluid support.
Existing packaged binaries do not automatically acquire this executable.

Expose separate `spike/coupled-surface-exchange-request/v1` and result/v1
through `run_coupled_surface_exchange`. An explicitly supplied overlap map
transfers outward heat/traction to opposite outward integrated heat/force,
with its paired adjoint reverse field. No automatic geometry/contact inference,
moment-preservation claim, time master, two-way FSI or flutter is introduced.

## Consequences and evidence

The existing CFD worker remains the composition root. Runtime paths stay in
trusted host configuration, never worker JSON. Unsupported regimes, stale
identity, malformed fields, numerical range failure, cancellation and partial
convergence fail explicitly. Production qualification stays false.

Methods, independently authored derivations and executed bounds are recorded in
[native CHT](../validation/NATIVE_CHT_METHOD_20261020.md) and
[surface exchange](../COUPLED_SURFACE_EXCHANGE.md). The
[staged plan](../INTERNAL_CFD_AND_FSI_PLAN.md) covers general meshes/enclosures,
exchangers, aerodynamics, turbulence, rotating machinery, broader fluid regimes
and structural/FSI coupling without promoting planned capabilities.

Existing approximate thermal/airflow adapters, SU2/OpenFOAM reference workflows,
explicit-lag co-simulation and unfinished PI/SI gates retain their semantics.
Knowledgeable human review and measured/platform/release qualification remain.
