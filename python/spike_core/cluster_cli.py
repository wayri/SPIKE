# SPDX-License-Identifier: Apache-2.0
"""Explicit administrator entry points for local pools and trusted LAN nodes."""
from __future__ import annotations

import ssl
import argparse
import json
from pathlib import Path

from .cluster_protocol import ClusterError, fingerprint, strict_json

COMMANDS = {"parallel-pool", "parallel-run", "cluster-probe", "cluster-run", "cluster-serve", "cluster-fingerprint", "cluster-discover"}


def register_commands(sub):
    sub.add_parser("parallel-pool", help="Report bounded CPU pool and actual accelerator backends")
    local = sub.add_parser("parallel-run", help="Run reviewed inline independent analysis jobs concurrently")
    local.add_argument("request", type=Path)
    for name in ("cluster-probe", "cluster-run"):
        parser = sub.add_parser(name, help="Contact only explicitly enrolled mutual-TLS worker nodes")
        parser.add_argument("enrollment", type=Path)
        if name == "cluster-run":
            parser.add_argument("request", type=Path)
    server = sub.add_parser("cluster-serve", help="Serve an explicitly trusted node; binds loopback unless configured")
    server.add_argument("configuration", type=Path)
    server.add_argument("--discoverable", action="store_true", help="Explicitly expose inert UDP LAN hints on port 41039")
    discovery = sub.add_parser("cluster-discover", help="List inert LAN hints; never enroll or execute")
    discovery.add_argument("--broadcast", default="255.255.255.255")
    cert = sub.add_parser("cluster-fingerprint", help="Print a public certificate SHA256 fingerprint for enrollment")
    cert.add_argument("certificate", type=Path)


def dispatch_cluster(args):
    if args.command == "cluster-discover":
        from .cluster_discovery import discover
        return discover(broadcast=args.broadcast)
    from .parallel_pool import pool_catalog, run_parallel_batch
    if args.command == "parallel-pool":
        return pool_catalog()
    if args.command == "parallel-run":
        return run_parallel_batch(_read(args.request))
    if args.command == "cluster-fingerprint":
        return {"fingerprint_sha256": fingerprint(ssl.PEM_cert_to_DER_cert(args.certificate.read_text(encoding="ascii")))}
    from .cluster_manager import load_pool, probe_pool, run_cluster_batch
    if args.command == "cluster-probe":
        return probe_pool(load_pool(args.enrollment))
    if args.command == "cluster-run":
        return run_cluster_batch(load_pool(args.enrollment), _read(args.request))
    from .cluster_transport import NodeServer
    config = _read(args.configuration)
    expected = {"contract", "certificate", "private_key", "trust_cert", "allowed_clients", "bind", "port",
                "max_concurrency", "max_threads_per_job", "max_timeout_s"}
    if set(config) != expected or config["contract"] != "spike/cluster-node/v1":
        raise ClusterError("SPIKE-CLUSTER-INPUT", "Invalid node configuration fields.")
    for key in ("certificate", "private_key", "trust_cert"):
        path = Path(config[key])
        config[key] = str((path if path.is_absolute() else args.configuration.parent / path).resolve(strict=True))
    server = NodeServer(config, catalog=pool_catalog, execute=run_parallel_batch)
    discovery = None
    try:
        if args.discoverable:
            from .cluster_discovery import DiscoveryResponder
            discovery = DiscoveryResponder(server.port)
        server.serve()
    except KeyboardInterrupt:
        pass
    finally:
        if discovery:
            discovery.close()
        server.close()
    return {"contract": "spike/cluster-stopped/v1", "state": "stopped"}


def _read(path):
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ClusterError("SPIKE-CLUSTER-LIMIT", "Input exceeds 4 MiB.")
    return strict_json(path.read_bytes())


def main(argv=None):
    """Dedicated entry avoids general service/extension initialization on nodes."""
    parser = argparse.ArgumentParser(description="SPIKE guarded parallel worker manager")
    register_commands(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(argv)
    try:
        result = dispatch_cluster(args)
        print(json.dumps(result, allow_nan=False))
        failed = any(job.get("state") in {"failed", "cancelled", "unknown"} or job.get("ok") is False
                     for job in result.get("jobs", result.get("outcomes", [])))
        failed = failed or any(node.get("state") != "ready" for node in result.get("nodes", []))
        return 2 if failed else 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error_code": getattr(exc, "code", "SPIKE-CLUSTER-INPUT"),
                          "error": "Worker manager failed; check enrollment, connectivity and resource limits."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
