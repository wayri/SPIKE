# SPIKES public equal-model benchmark protocol

Status: executable benchmark foundation; no public performance claim is
currently eligible.

`python/spikes/public_benchmark.py` closes an evidence-integrity gap in the
earlier small synthetic comparison. It defines immutable contracts for a
redistributable public corpus, same-byte engine adapters, per-engine run
evidence, and derived qualification.

## What “equal model” means

Every case binds all of the following:

- the exact deck SHA-256 and corpus-relative path;
- an exact model-bundle SHA-256;
- one or more named scalar metrics with identical references, reductions, and
  absolute/relative tolerances;
- source URL, retrieval time, SPDX license expression, license URL, artifact
  digest, explicit redistribution approval, reviewer, and review-evidence
  digest;
- one declared analysis and one size tier.

The JSON process adapter receives the exact deck bytes, not a generated
engine-specific approximation. Its result must attest the executed deck,
model-bundle, and benchmark-manifest digests. The executable and its fixed
argument vector are themselves content-addressed. A mismatch is an execution
error, not a skipped result.

An engine-specific wrapper may translate output formats and invoke its engine,
but it may not silently alter the supplied deck or model bundle. A genuinely
necessary engine compatibility rewrite belongs in a separately reviewed case;
it is not equal-model evidence.

## Performance-claim gate

`qualify_public_benchmark` derives status. Callers cannot set or override it.
A performance claim remains blocked unless:

1. all declared engines have evidence for every case;
2. exact manifest, deck, model-bundle, and metric sets match;
3. all accuracy tolerances pass;
4. the public corpus contains small, medium, and large tiers;
5. every run records at least five cold and five warm repetitions plus peak
   memory;
6. every run uses one pinned-host fingerprint and one timing scope; and
7. the claimant meets or beats every comparator for cold time, warm time, and
   peak memory on every case.

The repository now contains a deterministic first-party CC0 staged corpus in
`benchmarks/public_equal_model`: 16-, 500-, and 2,000-section resistor ladders.
The local 2026-08-31 Wave 6 run records five independent cold and five warm
process-inclusive repetitions plus peak working set for both SPIKES and
vendored ngspice 46. All six accuracy checks pass with zero scalar error. The
evidence is stored in
`artifacts/spikes-public-equal-model-wave6-final-2026-08-31.json`. The report
binds the current native DLL SHA-256
`0a7e631a9bae6b5d014704b63b6b4e628c8ae5d83d08c3ba3b48cf18e5ace2a4`.

This run does not establish a speed win. SPIKES uses less peak working set on
these cases (about 4.7 MiB versus 10.3-13.1 MiB), but its median
process-inclusive cold and warm times are slower than ngspice for all three
ladders. The report therefore must not be used to advertise performance
superiority.

This still does not authorize a superiority claim. The workspace has no Git
remote or authorized canonical HTTPS publication destination, so the CC0
corpus is locally staged rather than publicly retrievable. It also covers only
transparent sparse resistor scaling and two engines; it is not application,
analysis, compact-model, or multi-product breadth. The report keeps
`performance_claim_eligible` false and names those blockers.

The tests in `tests/python/test_spikes_public_benchmark.py` cover digest and
license enforcement, same-byte adapter attestation, incomplete-evidence
blocking, accuracy failure, and a fully populated synthetic qualification used
only to test the derivation logic.
