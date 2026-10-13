# SPDX-License-Identifier: Apache-2.0
"""Optional LAN hints. Discovery never grants trust or launches a connection."""
import json
import socket
import threading
import time
import uuid

from .cluster_protocol import ClusterError, integer, strict_json

CONTRACT = "spike/cluster-discovery/v1"


class DiscoveryResponder:
    def __init__(self, node_port, *, port=41039):
        self.node_port = integer(node_port, 1, 65535, "node port")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("0.0.0.0", integer(port, 1, 65535, "discovery port")))
        self.socket.settimeout(.25)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.socket.close()
        self.thread.join(timeout=1)

    def _serve(self):
        last = 0
        while not self.stop.is_set():
            try:
                data, peer = self.socket.recvfrom(513)
                now = time.monotonic()
                if len(data) > 512 or now - last < .1:
                    continue
                value = strict_json(data)
                if set(value) != {"contract", "nonce"} or value["contract"] != CONTRACT:
                    continue
                nonce = value["nonce"]
                if not isinstance(nonce, str) or len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
                    continue
                # Reply no larger than query: avoids a UDP reflection amplifier.
                reply = {"nonce": nonce, "port": self.node_port}
                self.socket.sendto(json.dumps(reply, separators=(",", ":")).encode("ascii"), peer)
                last = now
            except socket.timeout:
                continue
            except (OSError, ClusterError):
                if self.stop.is_set():
                    return


def discover(*, broadcast="255.255.255.255", port=41039, timeout_s=2):
    if not 0 < timeout_s <= 5:
        raise ClusterError("SPIKE-CLUSTER-LIMIT", "Discovery deadline must be at most five seconds.")
    nonce = uuid.uuid4().hex
    query = json.dumps({"contract": CONTRACT, "nonce": nonce}, separators=(",", ":")).encode("ascii")
    hints = set()
    deadline = time.monotonic() + timeout_s
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(query, (broadcast, integer(port, 1, 65535, "discovery port")))
        while time.monotonic() < deadline and len(hints) < 32:
            sock.settimeout(max(.001, deadline - time.monotonic()))
            try:
                data, peer = sock.recvfrom(513)
                if len(data) > 512:
                    continue
                value = strict_json(data)
                if set(value) == {"nonce", "port"} and value["nonce"] == nonce:
                    hints.add((peer[0], integer(value["port"], 1, 65535, "node port")))
            except socket.timeout:
                break
            except ClusterError:
                continue
    return {"contract": CONTRACT, "trust": "untrusted_hints_only", "nodes": [
        {"host": host, "port": port, "state": "approval_and_certificate_required"} for host, port in sorted(hints)]}
