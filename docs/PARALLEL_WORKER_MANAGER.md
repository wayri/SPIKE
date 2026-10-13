# SPIKE parallel worker manager

The source runtime supports bounded independent jobs locally or across explicitly
enrolled nodes. This change is **not in the previously built 0.3.9 installers**.
Parallel execution preserves each solver's numerical quality and validity limits.

## Local use

Open **Solver manager > Worker pool**, refresh, supply reviewed inline job JSON,
choose concurrency/threads, and Run. Cancel stops owned child processes. Each job
has its own outcome and provenance. This initial panel does not automatically
batch every study or enroll remote nodes.
Closing the pool panel cancels its active local batch.

```powershell
python -m python.spike_core.cluster_cli parallel-pool
python -m python.spike_core.cluster_cli parallel-run examples/parallel/harness-batch.json
```

Run from the repository root using SPIKE's Python environment. The ordinary CLI
also exposes these commands. Local MCP has `spike_parallel_pool` and
`spike_parallel_run`. Remote nodes should use the dedicated `cluster_cli` entry,
which avoids general service/extension initialization. Future rebuilt frozen
workers expose `--cluster` and internal `--parallel-child`; old installers do not.

The catalog's fixed allowlist includes inline harness PI/SI/MTL, straight-wire
RLGC, bounded channel airflow, compact thermal, AC PI, capacitor placement and
conversion-loss screening. Jobs cannot launch scripts, shells, extensions,
downloads, file imports or arbitrary executable paths.

## Hardware and resource limits

Intel/AMD CPUs use the existing CPU runtime, including high core count machines.
Thread budgets cap cooperative BLAS/OpenMP allocation; not every solver itself
is multithreaded. The existing accelerator catalog reports actual probes.
NVIDIA CuPy/CUDA readiness is shown only when detected; actual execution depends
on the solver. AMD/Intel GPU execution is not implemented.

Limits: 64 jobs/batch; eight concurrent child jobs/node; 32 requested threads/job,
bounded by detected CPU budget; 180 seconds/job; 900 seconds/batch; 4 MiB batch
input; 1 MiB/job input; 4 MiB/job output; 6 MiB retained batch output. Node policy
can lower these limits. CPU limits are cooperative, not OS containment. Portable
hard memory isolation and hostile multi-tenant execution are unsupported.

## Enroll trusted LAN nodes

1. Install matching SPIKE runtime versions and required dependencies on each
   trusted machine. Use a dedicated least-privileged OS account.
2. Have an administrator provision PEM certificates/private keys with suitable
   server/client purpose and server DNS/IP subject alternative names. Protect
   private keys with account-only filesystem permissions. Keep keys/enrollment
   outside `.spike` projects, Git and exports. Automatic certificate pairing and
   OS secret-store integration remain pending.
3. Exchange public certificates and fingerprints through a trusted channel:

   ```powershell
   python -m python.spike_core.cluster_cli cluster-fingerprint node.pem
   ```

4. On the node, create private administrator-controlled `node.json`:

   ```json
   {
     "contract": "spike/cluster-node/v1",
     "certificate": "node.pem",
     "private_key": "node.key",
     "trust_cert": "approved-client-certificates.pem",
     "allowed_clients": ["REPLACE_WITH_CLIENT_CERTIFICATE_SHA256"],
     "bind": "192.168.1.20",
     "port": 41038,
     "max_concurrency": 2,
     "max_threads_per_job": 1,
     "max_timeout_s": 180
   }
   ```

   Relative certificate paths resolve against this configuration directory.
   The transport defaults to loopback if no bind is supplied. Restrict firewall
   access to the coordinator; SPIKE never changes firewall rules. Start:

   ```powershell
   python -m python.spike_core.cluster_cli cluster-serve node.json
   ```

5. On the coordinator, create private `pool.json`:

   ```json
   {
     "contract": "spike/cluster-enrollment/v1",
     "identity": {"certificate": "client.pem", "private_key": "client.key"},
     "nodes": [{
       "id": "thermal-node-1",
       "host": "192.168.1.20",
       "port": 41038,
       "server_name": "node1.example.lan",
       "trust_cert": "node.pem",
       "fingerprint_sha256": "REPLACE_WITH_NODE_CERTIFICATE_SHA256"
     }]
   }
   ```

   TLS chain and hostname verification, exact node pin and approved client
   fingerprint are all required. Renewal requires deliberate re-enrollment.
   See [Python certificate verification](https://docs.python.org/3.11/library/ssl.html).

6. Probe all enrolled nodes, then submit reviewed jobs:

   ```powershell
   python -m python.spike_core.cluster_cli cluster-probe pool.json
   python -m python.spike_core.cluster_cli cluster-run pool.json examples/parallel/harness-batch.json
   ```

   All nodes must pass version, method and resource preflight. Jobs are
   partitioned in input order. Concurrency is per node, clamped to its assigned
   job count. Node/certificate identity and request/result digests are retained.
   One node admits one active batch. Delivery failures are **unknown**, never
   automatically retried: work might already have run. Disconnect cancels
   owned remote children. Ctrl+C stops the terminal operation. Durable queues,
   resumable transfers and remote desktop cancellation remain pending.

## Optional discovery

Start a node with `--discoverable` to expose inert UDP hints on port 41039.
Run `cluster-discover`, optionally `--broadcast 192.168.1.255`. Responses contain
address/TLS-port hints only and never trigger connections, enrollment, pin
replacement or simulation. Broadcast discovery normally stays within a subnet;
explicit TLS enrollment can use an administrator-controlled routed LAN/VPN.

## Diagnostics

| Code | Resolution |
| --- | --- |
| `SPIKE-CLUSTER-TRUST` | Independently verify certificates, pins, server name and chain; re-enroll deliberately. |
| `SPIKE-CLUSTER-INPUT` | Use exact fields, finite JSON, unique IDs and allowlisted inline inputs. |
| `SPIKE-CLUSTER-LIMIT` | Reduce concurrency, threads, dimensions, payload or runtime. |
| `SPIKE-CLUSTER-BUSY` | Wait for node work to finish; inspect uncertain results before retrying. |
| `SPIKE-CLUSTER-TRANSPORT` / `SPIKE-CLUSTER-TIMEOUT` | Check endpoint, firewall, TLS and runtime health. |
| `SPIKE-CLUSTER-UNAVAILABLE` / `SPIKE-CLUSTER-CAPABILITY` | Match versions, operations and dependencies before submitting. |
| `SPIKE-CLUSTER-PROVENANCE` | Reject the result and investigate node/runtime integrity. |
| `PARALLEL_JOB_TIMEOUT` / `PARALLEL_JOB_CANCELLED` | Owned process stopped; inspect individual outcome. |
| `PARALLEL_JOB_OUTPUT_LIMIT` | Reduce returned field dimensions; no silent truncation. |
| `PARALLEL_JOB_STRUCTURE_LIMIT` / `PARALLEL_JOB_BATCH_OUTPUT_LIMIT` | Reduce aggregate returned data or split the batch; retained results exceeded structural/byte bounds. |

## Evidence and unfinished scope

Tests use actual independent analyses, two separate loopback TLS node daemons,
missing/unapproved client certificates, wrong pin/hostname/chain, strict frames,
unsafe methods, resource limits, disconnect cancellation and altered provenance.
These do not qualify a physical LAN, a large cluster or vendor GPU hardware.

Single-solve MPI/domain decomposition, cross-node GPU allocation, automatic
certificate pairing, native remote-enrollment UI, persistent queue/recovery,
NUMA/affinity tuning and distributed transient coupling remain unsupported.
They require solver-specific contracts and independent numerical evidence.


## Retain jobs and results in a .spike project

In **External engines > Worker pool**, review the batch, run it, then save the
project with results included. The package retains the input draft and up to
32 batch records, including complete returned per-job results and execution
provenance. Open the project and expand **Saved batch results** to view a run;
no separate result file is required. **Load batch inputs** copies the original
request into the editor for explicit review before another run.

Catalog refresh never replaces saved concurrency/thread controls. Limits are
checked against this computer before a new run; a package created on a larger
machine does not grant additional resources here. A batch saved while running
has an interrupted record until its completion is saved. Opening a project
never reconnects to machines, resumes, retries or executes a batch.

**Save without results** and design exchange retain the input draft and omit
batch history. Local cluster enrollment files, hosts, certificate paths,
private keys and credentials are not portable project fields. Node identifiers
and certificate fingerprints in completed cluster provenance are evidence of
past execution, not enrollment or permission to contact a node. These jobs
carry their own explicit solver inputs: changing the displayed board does not
rebind a saved request or qualify its numerical results.

This is an additive v3 package capability. Older packages open with an empty
pool workspace. Existing installed releases need an updated build to expose
this panel and its saved history. This format change does not enable
single-solve partitioning or automatic cluster setup.
