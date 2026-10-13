# Portable parallel workspace

`spike/parallel-workspace/v1` is stored at canonical `analyses.parallel_execution`
and desktop v2 `analysis.parallel_execution`. Older projects without this field
display in the desktop with an empty history and draft values `[]`, `1`, `1`, `120` for jobs JSON,
concurrency, threads per job and timeout seconds. No migration executes a job,
contacts a node, enrolls a machine or resumes interrupted work. Missing canonical
and backend projection fields remain absent, preserving old analyses during
unrelated edits; the desktop presentation supplies defaults for missing state.

The draft contains four strings: `jobs_json`, `concurrency`, `threads_per_job`,
and `timeout_s`. Incomplete JSON and unfinished numeric edits survive saving.
The jobs text is limited to 4 MiB; each numeric text field to 128 characters.
Executable requests receive normal pool admission when explicitly submitted.

`runs` retains at most 32 unique portable IDs. Each record contains `id`, the
actual `spike/parallel-batch/v1` `request`, complete `result` (or null), and
`status`: completed, completed_with_errors, cancelled, failed or interrupted.
Optional `error` is at most 4096 characters. Completed states require a result.
An interrupted submission stores the admitted request and null result; reopening
does not imply the computation is still running. Removing results for a setup
export removes entire run records, preserving the editable draft.

Results retain the actual local `spike/parallel-batch-result/v1` or cluster
`spike/cluster-batch-result/v1` envelope, including future fields, complete job
outputs and provenance. The existing state-artifact mechanism externalizes
complete envelopes and supports deferred reads and lossless Save As. Admission
checks artifact hashes, batch request digest, job IDs/order/method/request
digests, and successful response digests using the pool's canonical JSON
algorithm. Cluster unknown-delivery outcomes remain explicitly unknown. Failed
child responses with worker metadata and response digests are checked against
their saved error envelope; supervisor failures have no child response digest.
These hashes establish
internal binding, not trusted remote attestation or numerical validity.

Admission limits the workspace to 96 MiB, two million JSON nodes, depth 48,
4096 keys per object and one million array items; numbers must be finite.
Requests use the existing pool contract and its resource maxima with a portable
256-thread admission budget, independent of the opening computer's CPU budget.
The execution-time budget is checked again only on explicit execution.

Enrollment, connection and credential fields (including host, private key,
certificate paths, tokens and passwords) are rejected recursively within this
workspace. Public node IDs and certificate fingerprints remain provenance.
Electrical `port_id` and mesh `nodes` are ordinary engineering data. PEM private
keys/certificates are rejected even in draft text; valid JSON draft text also
receives recursive key checks. Quoted credential keys in incomplete JSON are
also rejected. Unfinished JSON and arbitrary prose cannot be
reliably classified as containing every possible secret. Users must not paste
credentials into job drafts, free text or error messages. This is a portable
metadata boundary, not a general secret-detection guarantee.

Implementation: `project_parallel_state.py`; schema:
`schemas/parallel-workspace-v1.schema.json`; integration evidence:
`tests/python/test_project_parallel_state.py` (actual package write/read,
deferred Save As, real local analysis, cluster envelope, legacy defaults,
digest corruption, prohibited metadata and setup-only exports).
