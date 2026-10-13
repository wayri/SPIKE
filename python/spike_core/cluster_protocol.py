# SPDX-License-Identifier: Apache-2.0
"""Bounded, strict data framing for explicitly enrolled SPIKE nodes."""
from __future__ import annotations

import hashlib
import json
import math
import socket
import struct
import time

MAX_FRAME = 8 * 1024 * 1024
CONTRACT = "spike/cluster-wire/v1"


class ClusterError(ValueError):
    """Cluster failures are safe to display without credentials or payloads."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ClusterError("SPIKE-CLUSTER-INPUT", "Duplicate JSON keys are forbidden.")
        value[key] = item
    return value


def strict_json(data):
    if len(data) > MAX_FRAME:
        raise ClusterError("SPIKE-CLUSTER-LIMIT", "Message exceeds 8 MiB.")
    try:
        value = json.loads(data, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ClusterError("SPIKE-CLUSTER-INPUT", "Invalid strict JSON message.") from exc
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > 32 or count > 100000:
            raise ClusterError("SPIKE-CLUSTER-LIMIT", "Message nesting or collection budget exceeded.")
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ClusterError("SPIKE-CLUSTER-INPUT", "Nonfinite values are forbidden.")
    if not isinstance(value, dict):
        raise ClusterError("SPIKE-CLUSTER-INPUT", "Expected a JSON object.")
    return value


def encode(value):
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise ClusterError("SPIKE-CLUSTER-INPUT", "Message is not finite JSON.") from exc
    strict_json(data)
    return data


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ClusterError("SPIKE-CLUSTER-TIMEOUT", "Network deadline exceeded.")
    return remaining


def _read(sock, length, deadline):
    chunks = bytearray()
    while len(chunks) < length:
        sock.settimeout(_remaining(deadline))
        part = sock.recv(min(65536, length - len(chunks)))
        if not part:
            raise ClusterError("SPIKE-CLUSTER-TRANSPORT", "Peer closed a truncated message.")
        chunks.extend(part)
    return bytes(chunks)


def receive(sock, deadline):
    size = struct.unpack("!I", _read(sock, 4, deadline))[0]
    if not 1 <= size <= MAX_FRAME:
        raise ClusterError("SPIKE-CLUSTER-LIMIT", "Invalid frame length.")
    return strict_json(_read(sock, size, deadline))


def send(sock, value, deadline):
    data = encode(value)
    sock.settimeout(_remaining(deadline))
    sock.sendall(struct.pack("!I", len(data)) + data)


def fingerprint(der):
    return hashlib.sha256(der).hexdigest()


def pin(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ClusterError("SPIKE-CLUSTER-TRUST", "Require a lowercase SHA256 certificate fingerprint.")
    return value


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ClusterError("SPIKE-CLUSTER-INPUT", f"{name} must be an integer in {low}..{high}.")
    return value
