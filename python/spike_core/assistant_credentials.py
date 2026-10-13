# SPDX-License-Identifier: Apache-2.0
"""OS-protected assistant credentials. No file or environment fallback."""
from __future__ import annotations
import ctypes
import sys
from ctypes import wintypes

PROVIDERS = {"openai", "anthropic"}


def _native():
    if sys.platform != "win32":
        raise RuntimeError("Secure assistant credentials require Windows Credential Manager on this platform.")
    class Credential(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR)]
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredFree.argtypes = [ctypes.c_void_p]
    for name in ("CredWriteW", "CredReadW", "CredDeleteW"):
        getattr(api, name).restype = wintypes.BOOL
    api.CredFree.restype = None
    return api, Credential


def _target(provider):
    if provider not in PROVIDERS:
        raise ValueError("Credentials are supported only for official cloud providers.")
    return "SPIKE/assistant/" + provider


def get_credential(provider: str) -> str | None:
    target = _target(provider)
    api, credential_type = _native()
    ptr = ctypes.POINTER(credential_type)()
    if not api.CredReadW(target, 1, 0, ctypes.byref(ptr)):
        if ctypes.get_last_error() == 1168:
            return None
        raise RuntimeError("Cannot read the OS credential store.")
    try:
        return ctypes.string_at(ptr.contents.CredentialBlob, ptr.contents.CredentialBlobSize).decode("utf-8")
    finally:
        api.CredFree(ptr)


def set_credential(provider: str, key: str) -> None:
    target = _target(provider)
    if not isinstance(key, str) or not key.strip() or len(key.encode("utf-8")) > 2048 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError("Credential must contain 1–2048 printable non-space ASCII characters.")
    api, credential_type = _native()
    raw = key.encode("utf-8")
    blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    credential = credential_type(Type=1, TargetName=target, CredentialBlobSize=len(raw),
                                 CredentialBlob=blob, Persist=2, UserName="SPIKE")
    try:
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise RuntimeError("Cannot save to the OS credential store.")
    finally:
        ctypes.memset(blob, 0, len(raw))


def delete_credential(provider: str) -> None:
    target = _target(provider)
    api, _ = _native()
    if not api.CredDeleteW(target, 1, 0) and ctypes.get_last_error() != 1168:
        raise RuntimeError("Cannot delete from the OS credential store.")
