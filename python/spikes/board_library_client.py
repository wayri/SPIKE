# SPDX-License-Identifier: Apache-2.0
"""Explicit, hash-checked Python client for a trusted compiled board package."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import re
from types import MappingProxyType

from .board_library import CONTRACT, _hash
from .fault_injection import FaultSite


class _FaultDescriptor(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("element_id", ctypes.c_char_p),
                ("parameter", ctypes.c_char_p), ("healthy_value", ctypes.c_double),
                ("minimum", ctypes.c_double), ("maximum", ctypes.c_double),
                ("mechanism", ctypes.c_char_p)]


class BoardLibrary:
    """Verify generated files and the exact engine before executing native code.

    Hashes detect changes, not malicious authorship. Only load trusted packages.
    Dependencies of the engine remain the responsibility of its installation.
    """
    def __init__(self, manifest: str | Path, *, engine_library: str | Path):
        path = Path(manifest).resolve(strict=True)
        if path.stat().st_size > 1_048_576:
            raise ValueError("Board manifest exceeds 1 MiB")
        self.manifest = json.loads(path.read_text(encoding="utf-8"))
        record = self.manifest
        if record.get("contract") != CONTRACT or record.get("board_abi") != 1:
            raise ValueError("Unsupported compiled board manifest")
        files = record.get("files_sha256", {})
        if not isinstance(files, dict) or not 1 <= len(files) <= 32 or record.get("library") not in files:
            raise ValueError("Invalid board file inventory")
        for name, digest in files.items():
            if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
                raise ValueError("Manifest filenames must be direct children")
            candidate = (path.parent / name).resolve(strict=True)
            if candidate.parent != path.parent or not candidate.is_file() or candidate.stat().st_size > 128*1024*1024:
                raise ValueError("Invalid board artifact path or size")
            if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest) or _hash(candidate) != digest:
                raise ValueError(f"Board artifact hash mismatch: {name}")
        engine = Path(engine_library).resolve(strict=True)
        if record.get("engine", {}).get("kind") != "spikes-owned" or _hash(engine) != record["engine"].get("sha256"):
            raise ValueError("Engine does not match the board build provenance")
        self._dll_directory = os.add_dll_directory(str(engine.parent)) if os.name == "nt" else None
        self._engine = ctypes.CDLL(str(engine))
        self._engine.spikes_abi_version.restype = ctypes.c_uint32
        if self._engine.spikes_abi_version() != 1:
            raise ValueError("Engine ABI mismatch")
        fault_feature = "fault_injection_v1" in record.get("features", [])
        if fault_feature:
            required = ("spikes_transient_session_set_resistance",
                        "spikes_transient_session_set_mosfet_threshold")
            missing = [name for name in required if not hasattr(self._engine, name)]
            if missing:
                raise ValueError("Engine lacks required compiled-board fault symbols: " + ", ".join(missing))
        try:
            self._lib = ctypes.CDLL(str(path.parent / record["library"]))
        except OSError as exc:
            raise ValueError(f"Cannot load compiled board library: {exc}") from exc
        lib = self._lib
        p, d, s = ctypes.c_void_p, ctypes.c_double, ctypes.c_char_p
        lib.spikes_board_abi_version.restype = ctypes.c_uint32
        if lib.spikes_board_abi_version() != 1:
            raise ValueError("Board ABI mismatch")
        lib.spikes_board_engine_identity.restype = ctypes.c_size_t
        if lib.spikes_board_engine_identity() != ctypes.cast(self._engine.spikes_abi_version, ctypes.c_void_p).value:
            raise ValueError("Board linked a different loaded engine; start a clean process")
        signatures = {
            "create": (ctypes.POINTER(p),), "destroy": (p,), "error": (p,),
            "drive": (p, s, d), "step": (p, d), "read": (p, s, ctypes.POINTER(d)),
            "position": (p, ctypes.POINTER(d), ctypes.POINTER(ctypes.c_size_t)),
            "residual": (p, ctypes.POINTER(d)), "save": (p,), "restore": (p,), "reset": (p,),
        }
        for name, args in signatures.items():
            function = getattr(lib, "spikes_board_" + name)
            function.argtypes = args
            function.restype = s if name == "error" else None if name == "destroy" else ctypes.c_int
        fault_sites: dict[str, FaultSite] = {}
        if fault_feature:
            board_symbols = ("spikes_board_fault_api_version", "spikes_board_fault_count",
                             "spikes_board_fault_descriptor_at", "spikes_board_inject_fault",
                             "spikes_board_clear_fault", "spikes_board_clear_all_faults")
            missing = [name for name in board_symbols if not hasattr(lib, name)]
            if missing:
                raise ValueError("Board declares fault injection but lacks symbols: " + ", ".join(missing))
            lib.spikes_board_fault_api_version.restype = ctypes.c_uint32
            lib.spikes_board_fault_count.restype = ctypes.c_size_t
            lib.spikes_board_fault_descriptor_at.argtypes = (ctypes.c_size_t, ctypes.POINTER(_FaultDescriptor))
            lib.spikes_board_fault_descriptor_at.restype = ctypes.c_int
            lib.spikes_board_inject_fault.argtypes = (p, s, d)
            lib.spikes_board_inject_fault.restype = ctypes.c_int
            lib.spikes_board_clear_fault.argtypes = (p, s)
            lib.spikes_board_clear_fault.restype = ctypes.c_int
            lib.spikes_board_clear_all_faults.argtypes = (p,)
            lib.spikes_board_clear_all_faults.restype = ctypes.c_int
            if lib.spikes_board_fault_api_version() != 1:
                raise ValueError("Unsupported board fault API")
            manifest_sites = record.get("fault_sites")
            if not isinstance(manifest_sites, list) or len(manifest_sites) != lib.spikes_board_fault_count():
                raise ValueError("Board fault descriptors do not match manifest")
            for index, item in enumerate(manifest_sites):
                descriptor = _FaultDescriptor()
                if lib.spikes_board_fault_descriptor_at(index, ctypes.byref(descriptor)):
                    raise ValueError("Cannot read board fault descriptor")
                site = FaultSite(**{key: item[key] for key in (
                    "name", "element_id", "parameter", "healthy_value", "minimum", "maximum", "mechanism")})
                native = (descriptor.name.decode(), descriptor.element_id.decode(), descriptor.parameter.decode(),
                          descriptor.healthy_value, descriptor.minimum, descriptor.maximum, descriptor.mechanism.decode())
                declared = (site.name, site.element_id.upper(), site.parameter, site.healthy_value,
                            site.minimum, site.maximum, site.mechanism)
                if native != declared or site.name in fault_sites:
                    raise ValueError("Board fault descriptors do not match manifest")
                fault_sites[site.name] = site
        self.fault_sites = MappingProxyType(fault_sites)

    def create(self) -> "Board":
        return Board(self)


class Board:
    def __init__(self, library: BoardLibrary):
        self.library = library
        self._handle = ctypes.c_void_p()
        self._check(library._lib.spikes_board_create(ctypes.byref(self._handle)))

    @property
    def fault_sites(self):
        """Immutable named descriptors used by campaigns and environment mappings."""
        return self.library.fault_sites

    def _check(self, code: int) -> None:
        if code:
            message = self.library._lib.spikes_board_error(self._handle)
            raise RuntimeError(message.decode("utf-8", errors="replace") if message else "Board operation failed")

    def _call(self, method: str, *args) -> None:
        if not self._handle:
            raise RuntimeError("Board is closed")
        self._check(getattr(self.library._lib, "spikes_board_" + method)(self._handle, *args))

    @staticmethod
    def _name(name: str) -> bytes:
        if not isinstance(name, str) or not name or "\x00" in name:
            raise ValueError("Pin name must be nonempty text without NUL")
        return name.encode("utf-8")

    def drive(self, pin: str, volts: float) -> None:
        self._call("drive", self._name(pin), volts)

    def step(self, seconds: float) -> None:
        self._call("step", seconds)

    def read(self, output: str) -> float:
        value = ctypes.c_double()
        self._call("read", self._name(output), ctypes.byref(value))
        return value.value

    @property
    def time_s(self) -> float:
        return self.position()[0]

    def position(self) -> tuple[float, int]:
        time, steps = ctypes.c_double(), ctypes.c_size_t()
        self._call("position", ctypes.byref(time), ctypes.byref(steps))
        return time.value, steps.value

    def residual(self) -> float:
        value = ctypes.c_double()
        self._call("residual", ctypes.byref(value))
        return value.value

    def save(self) -> None:
        self._call("save")

    def restore(self) -> None:
        self._call("restore")

    def reset(self) -> None:
        self._call("reset")

    def inject_fault(self, name: str, value: float) -> None:
        try:
            site = self.library.fault_sites[name]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Unknown fault site: {name}") from exc
        self._call("inject_fault", self._name(name), site.validate(value))

    def clear_fault(self, name: str) -> None:
        if name not in self.library.fault_sites:
            raise ValueError(f"Unknown fault site: {name}")
        self._call("clear_fault", self._name(name))

    def clear_all(self) -> None:
        if self.library.fault_sites:
            self._call("clear_all_faults")

    def clear_all_faults(self) -> None:
        self.clear_all()

    def close(self) -> None:
        if self._handle:
            self.library._lib.spikes_board_destroy(self._handle)
            self._handle = ctypes.c_void_p()

    def __enter__(self) -> "Board":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def __del__(self) -> None:
        if getattr(self, "_handle", None):
            self.close()
