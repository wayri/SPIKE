# SPDX-License-Identifier: Apache-2.0
"""Serialize the final package identity check and replacement across processes."""
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def package_write_lock(path):
    name = hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode('utf-8')).hexdigest()
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        api.CreateMutexW.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.ReleaseMutex.argtypes = [wintypes.HANDLE]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.CreateMutexW(None, False, 'Local\\SPIKE-package-' + name)
        if not handle:
            raise OSError(ctypes.get_last_error(), 'Cannot acquire SPIKE package write mutex')
        acquired = False
        try:
            acquired = api.WaitForSingleObject(handle, 30000) in (0, 128)
            if not acquired:
                raise TimeoutError('SPIKE package is busy saving in another process')
            yield
        finally:
            if acquired:
                api.ReleaseMutex(handle)
            api.CloseHandle(handle)
    else:
        import fcntl
        import tempfile
        # A stable lock inode must survive unlock; deleting it creates split locks.
        directory = Path(tempfile.gettempdir()) / ('spike-package-locks-' + str(os.getuid()))
        directory.mkdir(mode=0o700, exist_ok=True)
        with open(directory / name, 'a+b') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def replace_package(temporary, destination, expected_digest):
    from .project_package import read_project, ProjectPackageError
    with package_write_lock(destination):
        if expected_digest is not None:
            current = read_project(destination, include_members=False)
            if current.manifest.get('manifest_payload_sha256') != expected_digest:
                raise ProjectPackageError('PROJECT_STALE: project changed while preparing this save')
        os.replace(temporary, destination)
