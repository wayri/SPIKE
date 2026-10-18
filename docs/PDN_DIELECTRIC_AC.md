# Finite dielectric AC admittance

PI02-S01 extends the supplied retained-dielectric path with conductivity and
dielectric loss. It solves actual complex fields independently at each supplied
frequency. It does not assign losses to a lossless field solution or infer PCB
geometry, conductor boundaries or material properties.

Call `extract_pdn_dielectric_ac(request)` from
`python/spike_core/pdn_dielectric_ac.py`, or send worker method
`extract_pdn_dielectric_ac` with exactly `{request: ...}`. The contract is
`spike/pdn-dielectric-ac-request/v1`; its installed offline schema describes
the structural boundary. Mesh, electrode and reference selection follow the
existing [finite electrostatic workflow](PDN_SCREENING.md).

Supply `frequencies_hz` and material records with `id`, `permittivity_f_m`,
`conductivity_s_m` and `loss_tangent`. Permittivity is a positive scalar or
symmetric positive-definite 3×3 tensor in F/m. Conductivity is a nonnegative
isotropic scalar in S/m. Loss tangent is a nonnegative scalar. No property is
inferred from a name. Frequencies are strictly positive and increasing; no DC
or interpolation is implied. Mesh coordinates explicitly use metres or
millimetres. Electrode voltages use RMS phasors with exp(+jωt).

Each basis solution drives one signal electrode to 1 V RMS and grounds all
others, including the named reference. Unassigned outer surfaces are insulating.
The finite domain is not an infinite/open-air field boundary. Signal ordering
follows the supplied electrode order with the reference removed.

## Derivation and independent checks

At angular frequency ω, the complex dielectric coefficient is
γ=σI+ω tanδ ε+jωε. Charge continuity and E=−∇φ give
−∇·(γ∇φ)=0. For affine tetrahedral shape functions, the local weak operator is
`Ke=volume × gradients × γ × gradientsᵀ`, in siemens. Summed electrode
reactions give currents entering the dielectric, including the reference.
Unit electrode solutions give multiport admittance Y, with
`I[receiver]=sum(Y[receiver,source] V[source])`.

Reciprocal material tensors imply Y=Yᵀ. If P contains basis potentials,
independent per-cell field integration gives `P† Kγ P=Y` because free-node
reactions vanish and fixed electrode values are real basis vectors. For any
complex voltage vector V, `V†YV=V†I` is the admittance power form (no factor
1/2 for RMS phasors). Conventional complex power `VᵀI*` is its conjugate;
the form's imaginary part is positive for capacitance under exp(+jωt).
Its real part is nonnegative integrated conductive/dielectric
loss; the Hermitian power matrix `(Y+Y†)/2` must be positive semidefinite.
All electrode currents sum to zero. The solver checks these invariants without
symmetry repair, eigenvalue clipping or fictitious damping.

Independent references are finite homogeneous plates (`Y=γ A/d`), layered
plates (`Y=A/sum(d_layer/γ_layer)`) and multielectrode gap networks. Different
layer loss tangents require complex voltage redistribution; agreement with the
series impedance oracle tests that actual complex solve. Mesh refinement
checks these aligned finite geometries, not arbitrary fringing structures.
The derivation, implementation and fixtures are original SPIKE work; no
external implementation, mesh or test dataset was used.

## Evidence and limits

Results use `spike/pdn-dielectric-ac-result/v1`, retain complex admittance,
node potentials, cell electric fields, reference/electrode/mesh lineage and
source/context digests. Diagnostics report free-node equation residuals,
conditioning, reciprocity, current conservation and integrated field-power
agreement. Status remains experimental and `production_qualified` is false.

Admission limits include 1000 nodes, 2000 cells, 128 free unknowns and
128 supplied frequencies, an explicit dense-work bound, 8 MiB input and
16 MiB estimated/actual output. Cancellation must abort without a partial
success result. Existing geometry audits reject invalid/nonconforming meshes
and unsupported electrode selections before solving.

This is an electroquasistatic finite-domain model. It does not solve magnetic
induction, radiation, conductor skin/proximity loss, packages or vias unless
their dielectric geometry and electrodes are explicitly supplied within this
model. Constant material loss tangent is only a supplied finite-band model;
these samples do not establish a passive causal time-domain macromodel. No
automatic attachment to the frequency-invariant transient network is performed.
Material dispersion, board-scale convergence and measured correlation remain
open PI02 gaps. Knowledgeable human numerical review remains required before
release under `CONTRIBUTING.md`.

## Stage verification

PI02-S01 is **Done** for its bounded acceptance: twelve stage tests passed
with zero skips in the [source-bound receipt](validation/parity/PI02-S01.json).
Independent aligned layered meshes with 9 and 75 free nodes have relative Y
errors below 2e-14 and conjugate field-power errors below 2e-14. Homogeneous
scalar/tensor plates, three tensor directions, lossless limits, multielectrode
power/current conservation and SI/mm scaling are tested. Corrupted solutions,
extreme norms, malformed inputs, resource limits, ill conditioning and
cancellation fail explicitly. The actual worker passed request and result schema
validation. No repaired, inferred or mocked solver response establishes Done.

All three affected prior PI/SI stages were re-executed and their source-bound
receipts refreshed. Pre-change receipts and logs remain historical evidence.
The architecture gate passed; full release checks and human release review
remain separate. PI02 as a whole is still in progress.

Combined PI/SI numerical, worker, electrostatic and evidence regressions passed
89 tests with zero skips in 23.239 s (`build/parity-pi02s01-focused.log`).
Retained execution logs preserve their exact bytes across Git line-ending
conversion so their source-bound hashes remain reproducible.
