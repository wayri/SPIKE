"""Operating-system containment for the sparseLizard process adapter."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence


class SparseLizardAdapterError(RuntimeError):
    """Raised when the bounded sparseLizard process contract is not satisfied."""


def _limited_reader(stream: Any, limit: int, captured: List[bytes], exceeded: threading.Event) -> None:
    total = 0
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            total += len(chunk)
            if total > limit:
                exceeded.set()
                return
            captured.append(chunk)
    finally:
        stream.close()


def _adapter_environment() -> Dict[str, str]:
    allowed = (
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME",
        "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "LANG", "LC_ALL",
    )
    return {key: os.environ[key] for key in allowed if os.environ.get(key)}


def _resource_preexec(memory_limit_mb: int, timeout_s: int, output_limit_bytes: int):
    if os.name == "nt":
        return None
    try:
        import resource
    except ImportError:
        return None

    def apply() -> None:
        memory = memory_limit_mb * 1024**2
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (timeout_s + 2, timeout_s + 3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit_bytes, output_limit_bytes))

    return apply


class _WindowsJob:
    """Own a kill-on-close Job Object with a hard per-process memory limit."""

    def __init__(
        self, process: subprocess.Popen[bytes], memory_limit_mb: int,
        timeout_s: int, active_process_limit: int = 1,
    ) -> None:
        self.handle: Any = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong), ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong), ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong), ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BASIC_LIMITS(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class EXTENDED_LIMITS(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC_LIMITS), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise SparseLizardAdapterError(f"Unable to create Windows Job Object (error {ctypes.get_last_error()}).")
        limits = EXTENDED_LIMITS()
        # PROCESS_TIME | ACTIVE_PROCESS | PROCESS_MEMORY | KILL_ON_JOB_CLOSE |
        # DIE_ON_UNHANDLED_EXCEPTION. ActiveProcessLimit=1 prevents the native
        # model host from creating helper processes after Job assignment.
        limits.BasicLimitInformation.LimitFlags = (
            0x00000002 | 0x00000008 | 0x00000100 | 0x00000400 | 0x00002000
        )
        limits.BasicLimitInformation.PerProcessUserTimeLimit = int((timeout_s + 1) * 10_000_000)
        limits.BasicLimitInformation.ActiveProcessLimit = active_process_limit
        limits.ProcessMemoryLimit = memory_limit_mb * 1024**2
        if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise SparseLizardAdapterError(f"Unable to configure sparseLizard memory limits (error {error}).")
        ui_restrictions = wintypes.DWORD(0x000000FF)
        if not kernel32.SetInformationJobObject(
            handle, 4, ctypes.byref(ui_restrictions), ctypes.sizeof(ui_restrictions)
        ):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise SparseLizardAdapterError(f"Unable to configure Windows Job UI restrictions (error {error}).")
        if not kernel32.AssignProcessToJobObject(handle, wintypes.HANDLE(process._handle)):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise SparseLizardAdapterError(f"Unable to contain sparseLizard in a Windows Job Object (error {error}).")
        self.handle = handle
        self._kernel32 = kernel32

    def terminate(self) -> None:
        if self.handle is not None:
            self._kernel32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle is not None:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None


def _resume_windows_process(process: subprocess.Popen[bytes]) -> bool:
    """Resume every initial thread after the process is assigned to its Job.

    ``subprocess`` closes the primary thread handle returned by CreateProcess,
    so enumerate the still-suspended process threads and resume them by ID.
    No untrusted instruction can execute between creation and Job assignment.
    """

    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = (wintypes.HANDLE, ctypes.POINTER(THREADENTRY32))
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = (wintypes.HANDLE, ctypes.POINTER(THREADENTRY32))
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.ResumeThread.argtypes = (wintypes.HANDLE,)
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if not snapshot or snapshot == invalid_handle:
        raise SparseLizardAdapterError(
            f"Unable to enumerate suspended process threads (error {ctypes.get_last_error()})."
        )
    resumed = 0
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        present = bool(kernel32.Thread32First(snapshot, ctypes.byref(entry)))
        while present:
            if entry.th32OwnerProcessID == process.pid:
                thread = kernel32.OpenThread(0x0002, False, entry.th32ThreadID)
                if not thread:
                    raise SparseLizardAdapterError(
                        f"Unable to open suspended process thread (error {ctypes.get_last_error()})."
                    )
                try:
                    previous = kernel32.ResumeThread(thread)
                    if previous == 0xFFFFFFFF:
                        raise SparseLizardAdapterError(
                            f"Unable to resume contained process (error {ctypes.get_last_error()})."
                        )
                    resumed += 1
                finally:
                    kernel32.CloseHandle(thread)
            present = bool(kernel32.Thread32Next(snapshot, ctypes.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)
    if resumed == 0:
        raise SparseLizardAdapterError("Contained process had no resumable initial thread.")
    return True


def _terminate_process_tree(process: subprocess.Popen[bytes], windows_job: _WindowsJob | None = None) -> None:
    if process.poll() is not None:
        return
    if windows_job is not None and windows_job.handle is not None:
        windows_job.terminate()
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        process.kill()


def run_adapter_process(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_s: int,
    memory_limit_mb: int,
    output_limit_bytes: int,
    stream_limit_bytes: int,
    cancellation_event: threading.Event | None = None,
    stdin_payload: bytes | None = None,
    windows_active_process_limit: int = 1,
) -> Dict[str, Any]:
    """Run one local executable with bounded time, memory, files, and streams."""

    windows_suspended = os.name == "nt"
    process = subprocess.Popen(
        list(command), cwd=str(cwd), stdin=subprocess.PIPE if stdin_payload is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_adapter_environment(),
        preexec_fn=_resource_preexec(memory_limit_mb, timeout_s, output_limit_bytes),
        start_new_session=os.name != "nt",
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | (0x00000004 if windows_suspended else 0)
            if os.name == "nt" else 0
        ),
    )
    try:
        windows_job = _WindowsJob(
            process, memory_limit_mb, timeout_s, windows_active_process_limit
        ) if os.name == "nt" else None
        suspended_before_job_assignment = _resume_windows_process(process)
    except Exception:
        _terminate_process_tree(process)
        process.wait(timeout=10)
        raise
    if stdin_payload is not None and process.stdin is not None:
        try:
            process.stdin.write(stdin_payload)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    overflow = threading.Event()
    stdout_chunks: List[bytes] = []
    stderr_chunks: List[bytes] = []
    readers = [
        threading.Thread(target=_limited_reader, args=(process.stdout, stream_limit_bytes, stdout_chunks, overflow), daemon=True),
        threading.Thread(target=_limited_reader, args=(process.stderr, stream_limit_bytes, stderr_chunks, overflow), daemon=True),
    ]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout_s
    timed_out = False
    cancelled = False
    while process.poll() is None:
        if cancellation_event is not None and cancellation_event.is_set():
            cancelled = True
            _terminate_process_tree(process, windows_job)
            break
        if overflow.is_set() or time.monotonic() >= deadline:
            timed_out = not overflow.is_set()
            _terminate_process_tree(process, windows_job)
            break
        time.sleep(0.05)
    try:
        return_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process, windows_job)
        return_code = process.wait(timeout=5)
    for reader in readers:
        reader.join(timeout=2)
    try:
        if overflow.is_set():
            raise SparseLizardAdapterError("Adapter stdout or stderr exceeded its configured output limit.")
        if timed_out:
            raise SparseLizardAdapterError(f"Adapter exceeded the {timeout_s}-second execution timeout.")
        if cancelled:
            raise SparseLizardAdapterError("SparseLizard adapter execution was cancelled.")
        return {
            "return_code": return_code,
            "stdout": b"".join(stdout_chunks).decode("utf-8", errors="replace"),
            "stderr": b"".join(stderr_chunks).decode("utf-8", errors="replace"),
            "memory_limit_enforced": True,
            "suspended_before_job_assignment": suspended_before_job_assignment,
            "job_assignment_race_closed": suspended_before_job_assignment,
        }
    finally:
        if windows_job is not None:
            windows_job.close()
