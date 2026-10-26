<!-- SPDX-License-Identifier: Apache-2.0 -->

# SI08-I01 finite interoperability campaign

This campaign closes only named network import, explicit physical pairing and
neutral export composition. Existing `sparameters` and `sparameter_modes` own
all numerical operations. Their mathematics is unchanged. The offline example
retains original UTF-8 input bytes as text, SHA-256 identity, explicitly supplied
ordered names, operation maps and a separately owned derived network. It never
infers connector names from a file that does not supply them.

The derived capture retains frequency in Hz, S[receiver,source], positive real
per-port references in ohms, D-pair/C-pair/unpaired ordering and power-normalized
wave convention. Differential/common references generally differ. The existing
Touchstone 1 writer rejects that export; neutral JSON retains the complete
reference vector and name mapping. This does not claim a new Touchstone 2 writer
or an automatic conversion to a shared reference. The example is not a public
worker/schema or instrument acquisition interface; those remain I03/I07 targets.

## Frozen acceptance

The five integrated witnesses use original independently specified unequal
forward/reverse values, four frequency scales, RI/MA/dB, full three-port
receiver-major data, DC, unequal references, unpaired names and reversed pair
polarity. Expected values are fixed physical answers, not writer/reader round
trips. Invalid identity/partition/source records must fail. Absolute tolerance
is 3e-16 for the small fixed matrices, with no fitted or physical error claim.

The [independent oracle](validation/SI08_I01_INTEROP_ORACLE_20261025.md) derives
the voltage/current basis, reviews primary references and records its additional
domain, conditioning, permutation and ownership checks. All supported port counts
are exercised; parameter space is not exhaustively enumerated. No empirical
convergence order is relevant to an exact finite basis change; algebraic residuals
and tolerance-bounded roundoff are the acceptance quantities.

`scripts/verify_si08_interoperability.py` executes integrated and independent
witnesses plus the original seven mixed-mode regressions. It binds source bytes
before/after, exact test identities/outcomes and retained log. A separate
adversarial test rejects stale source, missing coverage, skips and overclaimed
scope. The finite checklist admits I01 only through this current gate.

## Integration and qualification targets

After I01, finish I02 causal/noncausal/DC/grid witnesses, I03 operational
calibration and I05 automatic passive fitting; then I06 loaded use, I07 complete
worker/native workflows and I08 integrated evidence. The existing eight-point
scope remains frozen. Measured E01/E02 and human/installed R01/R02 stay separate.

The qualification owner released its source freeze on 25 October 2026. SI08-S05
still needs correctly targeted candidate-native wide/narrow, invalidation,
singular-second-sample failure and recovery captures. Its old native receipt is
not currently source-qualified. Execution review stopped the previous native
automation; this campaign does not retry it through an alternate path.

Full-suite qualification is incomplete: the prior complete run failed and the
corrected run was interrupted by a disk-capacity incident. No large rerun is
launched here. Capacity recovery and a genuine stable-source full rerun remain
required. No measured corpus is available. None of these blockers is converted
into a passing implementation, physical or release claim.
