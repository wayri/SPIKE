# SPDX-License-Identifier: Apache-2.0
"""GUI-terminal-compatible orchestration of explicitly enrolled worker nodes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import uuid

from . import __version__
from .cluster_protocol import CONTRACT, ClusterError, digest, encode, integer, pin, strict_json
from .cluster_transport import node_request


def load_pool(path):
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ClusterError("SPIKE-CLUSTER-LIMIT", "Enrollment file exceeds 64 KiB.")
    config = strict_json(path.read_bytes())
    if set(config) != {"contract", "identity", "nodes"} or config["contract"] != "spike/cluster-enrollment/v1":
        raise ClusterError("SPIKE-CLUSTER-INPUT", "Invalid enrollment contract.")
    if not isinstance(config["identity"], dict) or set(config["identity"]) != {"certificate", "private_key"}:
        raise ClusterError("SPIKE-CLUSTER-INPUT", "Enrollment requires a local client certificate and private key.")
    nodes = config["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 32:
        raise ClusterError("SPIKE-CLUSTER-LIMIT", "Enroll 1..32 nodes.")
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "host", "port", "server_name", "trust_cert", "fingerprint_sha256"}:
            raise ClusterError("SPIKE-CLUSTER-INPUT", "Invalid node enrollment fields.")
        for key in ("id", "host", "server_name", "trust_cert"):
            if not isinstance(node[key], str) or not 1 <= len(node[key]) <= 1024 or any(ord(c) < 32 for c in node[key]):
                raise ClusterError("SPIKE-CLUSTER-INPUT", "Invalid node identity or endpoint.")
        if node["id"] in ids:
            raise ClusterError("SPIKE-CLUSTER-INPUT", "Duplicate enrolled node identity.")
        ids.add(node["id"])
        integer(node["port"], 1, 65535, "port")
        pin(node["fingerprint_sha256"])
    # All configuration paths belong to the administrator, never to jobs or discovery.
    for item, keys in [(config["identity"], ("certificate", "private_key"))] + [(n, ("trust_cert",)) for n in nodes]:
        for key in keys:
            source = Path(item[key])
            item[key] = str((source if source.is_absolute() else path.parent / source).resolve(strict=True))
    return config


def _call(node, identity, method, batch=None, *, timeout_s=30):
    identifier = uuid.uuid4().hex
    request = {"contract": CONTRACT, "id": identifier, "method": method}
    if batch is not None:
        request["batch"] = batch
    reply = node_request(node, identity, request, timeout_s=timeout_s)
    if reply.get("ok") is not True:
        raise ClusterError("SPIKE-CLUSTER-REMOTE", "Node rejected work; no automatic replay. Check node health and limits.")
    if reply.get("contract") != CONTRACT or reply.get("id") != identifier or not isinstance(reply.get("result"), dict):
        raise ClusterError("SPIKE-CLUSTER-TRANSPORT", "Node response identity or contract mismatch.")
    return reply["result"]


def probe_pool(config):
    records = []
    with ThreadPoolExecutor(max_workers=min(8, len(config["nodes"]))) as executor:
        pending = {executor.submit(_call, n, config["identity"], "catalog"): n for n in config["nodes"]}
        for future in as_completed(pending):
            node = pending[future]
            try:
                catalog = future.result()
                compatible = catalog.get("worker_version") == __version__
                records.append({"id": node["id"], "state": "ready" if compatible else "version_mismatch", "catalog": catalog})
            except (OSError, ValueError, KeyError) as exc:
                records.append({"id": node["id"], "state": "unavailable", "error_code": getattr(exc, "code", "SPIKE-CLUSTER-TRANSPORT")})
    return {"contract": "spike/cluster-status/v1", "nodes": sorted(records, key=lambda n: n["id"])}


def run_cluster_batch(config, request):
    """Distribute independent jobs; never automatically retry an uncertain solve."""
    from .parallel_pool import validate_batch
    request = validate_batch(request, cpu_budget=256)
    status = probe_pool(config)
    usable = [row for row in status["nodes"] if row["state"] == "ready"]
    if len(usable) != len(config["nodes"]):
        raise ClusterError("SPIKE-CLUSTER-UNAVAILABLE", "All enrolled nodes must pass preflight; no work submitted.")
    for row in usable:
        methods = row["catalog"].get("allowed_methods", [])
        if any(job["method"] not in methods for job in request["jobs"]):
            raise ClusterError("SPIKE-CLUSTER-CAPABILITY", "A node cannot run requested methods; no work submitted.")
    partitions = []
    catalogs = {row["id"]: row["catalog"] for row in usable}
    for index, node in enumerate(config["nodes"]):
        jobs = request["jobs"][index::len(usable)]
        if not jobs:
            continue
        batch = {**request, "jobs": jobs, "concurrency": min(request["concurrency"], len(jobs))}
        limits = catalogs[node["id"]].get("limits", {})
        if (batch["concurrency"] > limits.get("max_concurrency", 0)
                or batch["threads_per_job"] > limits.get("max_threads_per_job", 0)
                or batch["concurrency"] * batch["threads_per_job"] > limits.get("max_total_cpu_threads", 0)
                or batch["timeout_s"] > limits.get("max_timeout_s", 0)):
            raise ClusterError("SPIKE-CLUSTER-LIMIT", "Batch exceeds enrolled node resource limits; no work submitted.")
        partitions.append((node, batch))
    outcomes = {}
    with ThreadPoolExecutor(max_workers=min(32, len(usable))) as executor:
        pending = {}
        for node, batch in partitions:
            pending[executor.submit(_call, node, config["identity"], "batch", batch, timeout_s=910)] = (node, batch)
        for future in as_completed(pending):
            node, batch = pending[future]
            jobs = batch["jobs"]
            try:
                result = future.result()
                returned = result.get("outcomes")
                provenance = result.get("provenance")
                if not isinstance(provenance, dict) or provenance.get("request_sha256") != digest(batch):
                    raise ClusterError("SPIKE-CLUSTER-PROVENANCE", "Node request digest mismatch.")
                if (not isinstance(returned, list) or any(not isinstance(job, dict) for job in returned)
                        or [job.get("id") for job in returned] != [job["id"] for job in jobs]):
                    raise ClusterError("SPIKE-CLUSTER-PROVENANCE", "Node job identity mismatch.")
                for job, expected in zip(returned, jobs):
                    lineage = job.get("provenance")
                    if (job.get("method") != expected["method"] or type(job.get("ok")) is not bool
                            or not isinstance(lineage, dict) or lineage.get("request_sha256") != digest(expected)):
                        raise ClusterError("SPIKE-CLUSTER-PROVENANCE", "Node job provenance mismatch.")
                    if job["ok"]:
                        response = {"id": job["id"], "ok": True, "result": job.get("result"), "meta": job.get("worker_meta")}
                        if lineage.get("response_sha256") != digest(response):
                            raise ClusterError("SPIKE-CLUSTER-PROVENANCE", "Node result digest mismatch.")
                for job in returned:
                    outcomes[job["id"]] = {**job, "node_id": node["id"], "node_certificate_sha256": node["fingerprint_sha256"]}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                for job in jobs:
                    outcomes[job["id"]] = {"id": job["id"], "node_id": node["id"], "state": "unknown",
                        "error_code": getattr(exc, "code", "SPIKE-CLUSTER-TRANSPORT"),
                        "error": "Delivery or result verification failed; work may have run. No replay performed."}
    return {"contract": "spike/cluster-batch-result/v1", "request_sha256": digest(request),
            "jobs": [outcomes[job["id"]] for job in request["jobs"]], "execution": "independent_jobs",
            "distributed_single_solve": "unsupported"}
