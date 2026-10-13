# SPDX-License-Identifier: Apache-2.0
"""Mutually authenticated transport; no project paths or executable requests."""
from __future__ import annotations

import socket
import ssl
import threading
import time

from .cluster_protocol import (CONTRACT, ClusterError, fingerprint, integer, pin,
                               receive, send)


def tls_context(config, *, server):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=config["trust_cert"])
    context.load_cert_chain(config["certificate"], config["private_key"])
    return context


def node_request(node, identity, request, *, timeout_s=30):
    """Use only host-enrolled configuration, never hints as trust material."""
    deadline = time.monotonic() + timeout_s
    port = integer(node["port"], 1, 65535, "port")
    expected = pin(node["fingerprint_sha256"])
    context = tls_context({**identity, "trust_cert": node["trust_cert"]}, server=False)
    with socket.create_connection((node["host"], port), timeout=timeout_s) as raw:
        raw.settimeout(max(.001, deadline - time.monotonic()))
        with context.wrap_socket(raw, server_hostname=node["server_name"]) as sock:
            if fingerprint(sock.getpeercert(binary_form=True)) != expected:
                raise ClusterError("SPIKE-CLUSTER-TRUST", "Node certificate does not match enrollment.")
            send(sock, request, deadline)
            return receive(sock, deadline)


class NodeServer:
    """One admitted batch per node; capped clients before handshake allocation."""
    def __init__(self, config, *, catalog, execute):
        self.config, self.catalog, self.execute = config, catalog, execute
        self.context = tls_context(config, server=True)
        self.clients = {pin(value) for value in config["allowed_clients"]}
        if not self.clients:
            raise ClusterError("SPIKE-CLUSTER-TRUST", "No approved clients; refusing to listen.")
        self.slots = threading.BoundedSemaphore(4)
        self.batch_slot = threading.Lock()
        self.stop_event = threading.Event()
        self.active = set()
        self.active_lock = threading.Lock()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((config.get("bind", "127.0.0.1"), integer(config["port"], 0, 65535, "port")))
        self.socket.listen(4)
        self.socket.settimeout(.25)
        self.port = self.socket.getsockname()[1]

    def close(self):
        self.stop_event.set()
        self.socket.close()
        with self.active_lock:
            for sock in tuple(self.active):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def serve(self):
        while not self.stop_event.is_set():
            try:
                raw, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                if self.stop_event.is_set():
                    break
                raise
            if not self.slots.acquire(blocking=False):
                raw.close()
                continue
            threading.Thread(target=self._client, args=(raw,), daemon=True).start()

    def _client(self, raw):
        sock, acquired = raw, False
        disconnected = threading.Event()
        watcher_stop = threading.Event()
        watcher = None
        with self.active_lock:
            self.active.add(raw)
        try:
            raw.settimeout(5)
            sock = self.context.wrap_socket(raw, server_side=True)
            with self.active_lock:
                self.active.discard(raw)
                self.active.add(sock)
            if fingerprint(sock.getpeercert(binary_form=True)) not in self.clients:
                raise ClusterError("SPIKE-CLUSTER-TRUST", "Client identity is not approved.")
            request = receive(sock, time.monotonic() + 5)
            method = request.get("method")
            expected = {"contract", "id", "method"} | ({"batch"} if method == "batch" else set())
            if set(request) != expected or request.get("contract") != CONTRACT or method not in {"catalog", "batch"}:
                raise ClusterError("SPIKE-CLUSTER-INPUT", "Unsupported cluster request.")
            if not isinstance(request["id"], str) or not 1 <= len(request["id"]) <= 128:
                raise ClusterError("SPIKE-CLUSTER-INPUT", "Invalid request identity.")
            if method == "catalog":
                result = self.catalog()
                result = {**result, "limits": {**result.get("limits", {}),
                    "max_concurrency": min(result["limits"]["max_concurrency"], self.config.get("max_concurrency", 2)),
                    "max_threads_per_job": min(result["limits"]["max_threads_per_job"], self.config.get("max_threads_per_job", 1)),
                    "max_timeout_s": min(result["limits"]["max_timeout_s"], self.config.get("max_timeout_s", 180))}}
            else:
                acquired = self.batch_slot.acquire(blocking=False)
                if not acquired:
                    raise ClusterError("SPIKE-CLUSTER-BUSY", "Node is busy; submit later. No automatic replay.")
                batch = request["batch"]
                if not isinstance(batch, dict):
                    raise ClusterError("SPIKE-CLUSTER-INPUT", "Expected a batch object.")
                for key, default in (("concurrency", 2), ("threads_per_job", 1)):
                    limit = integer(self.config.get("max_" + key, default), 1, 32, "node " + key)
                    integer(batch.get(key), 1, limit, key)
                timeout = batch.get("timeout_s")
                if type(timeout) not in (int, float) or not 0 < timeout <= self.config.get("max_timeout_s", 180):
                    raise ClusterError("SPIKE-CLUSTER-LIMIT", "Job timeout exceeds node policy.")
                # Extra data, disconnect, or shutdown cancel owned child processes.
                def watch():
                    sock.settimeout(.2)
                    while not watcher_stop.is_set():
                        try:
                            sock.recv(1)
                            disconnected.set()
                            return
                        except socket.timeout:
                            continue
                        except OSError:
                            disconnected.set()
                            return
                watcher = threading.Thread(target=watch, daemon=True)
                watcher.start()
                started = time.monotonic()
                result = self.execute(batch, cancel_check=lambda:
                    disconnected.is_set() or self.stop_event.is_set() or time.monotonic() - started > 900)
                watcher_stop.set()
                watcher.join(timeout=1)
            send(sock, {"contract": CONTRACT, "id": request["id"], "ok": True, "result": result}, time.monotonic() + 5)
        except (ClusterError, ValueError, KeyError, RuntimeError, TypeError) as exc:
            try:
                send(sock, {"contract": CONTRACT, "ok": False,
                     "error_code": getattr(exc, "code", "SPIKE-CLUSTER-INPUT"),
                     "error": "Cluster request rejected; check node enrollment, input and resource limits."}, time.monotonic() + 1)
            except (OSError, ClusterError):
                pass
        except OSError:
            pass  # Authentication/disconnect failures disclose neither credentials nor inputs.
        finally:
            watcher_stop.set()
            disconnected.set()
            if acquired:
                self.batch_slot.release()
            with self.active_lock:
                self.active.discard(raw)
                self.active.discard(sock)
            sock.close()
            self.slots.release()
