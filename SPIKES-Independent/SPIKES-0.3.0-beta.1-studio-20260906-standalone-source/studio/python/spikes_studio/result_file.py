"""SPIKES Studio result archive: explicit time, lossless chunks, provenance."""
from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile
import numpy as np
from .signal_math import SignalMath, Quantity, Unit


CONTRACT = "spikes/result-archive/v1"


def save_result(path, engine: SignalMath, provenance, chunk_samples=4096):
    if not 1 <= chunk_samples <= 65536: raise ValueError("Invalid chunk size")
    names = list(engine.signals)
    manifest = {"contract": CONTRACT, "provenance": provenance, "sample_count": len(engine.time),
        "signals": [{"name": n, "unit_powers": engine.signals[n].unit.powers} for n in names],
        "chunk_samples": chunk_samples, "time": "explicit_seconds", "lossy": False}
    # Exclusive creation: caller must explicitly handle an existing result file.
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, allow_nan=False))
        for start in range(0, len(engine.time), chunk_samples):
            end = min(start + chunk_samples, len(engine.time))
            arrays = {"time": engine.time[start:end]} | {f"s{i}": engine.signals[n].values[start:end] for i, n in enumerate(names)}
            for key, values in arrays.items():
                buffer = io.BytesIO()
                np.save(buffer, values, allow_pickle=False)
                archive.writestr(f"chunks/{start:012d}/{key}.npy", buffer.getvalue())


def load_result(path, max_bytes=256 * 1024 * 1024):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) != len({e.filename for e in entries}): raise ValueError("Duplicate archive entry")
        if sum(e.file_size for e in entries) > max_bytes: raise ValueError("Uncompressed result exceeds read budget")
        if archive.getinfo("manifest.json").file_size > 1024 * 1024: raise ValueError("Manifest too large")
        meta = json.loads(archive.read("manifest.json"))
        if meta.get("contract") != CONTRACT or meta.get("lossy") is not False: raise ValueError("Unsupported result archive")
        count, chunk = meta["sample_count"], meta["chunk_samples"]
        if not 2 <= count <= 2_000_000 or not 1 <= chunk <= 65536: raise ValueError("Invalid archive dimensions")
        names = [s["name"] for s in meta["signals"]]
        if len(set(names)) != len(names) or len(names) > 1024: raise ValueError("Invalid signal index")
        columns = [[] for _ in range(len(names) + 1)]
        for start in range(0, count, chunk):
            for i, key in enumerate(["time"] + [f"s{k}" for k in range(len(names))]):
                values = np.load(io.BytesIO(archive.read(f"chunks/{start:012d}/{key}.npy")), allow_pickle=False)
                if values.shape != (min(chunk, count-start),) or values.dtype.kind not in "fc": raise ValueError("Invalid numeric chunk")
                columns[i].append(values)
        time = np.concatenate(columns[0])
        signals = {n: Quantity(np.concatenate(columns[i+1]), Unit(tuple(meta["signals"][i]["unit_powers"]))) for i, n in enumerate(names)}
        return SignalMath(time, signals), meta["provenance"]
