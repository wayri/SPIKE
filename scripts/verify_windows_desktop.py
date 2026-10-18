# SPDX-License-Identifier: Apache-2.0
"""Require embedded frontend and native panel lifecycle acceptance on Windows.

Runs only the fixed inert qualification page in a disposable WebView2 profile.
This is not normal workspace, installer, solver or clean-machine acceptance.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from typing import Callable

PASS_TITLE = "SPIKE PANEL QUALIFICATION PASS - native portal, draft, action, redock, close and zero leftover frames"
FAIL_TITLE = "SPIKE PANEL QUALIFICATION FAIL"


def await_qualification(process, titles: Callable[[], list[str]], *, timeout: float = 45,
                        clock=time.monotonic, sleep=time.sleep) -> str:
    deadline = clock() + timeout
    last_titles: list[str] = []
    while clock() < deadline:
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"Desktop exited before frontend qualification (exit {code}).")
        last_titles = titles()
        failure = next((title for title in last_titles if title.startswith(FAIL_TITLE)), None)
        if failure:
            raise RuntimeError(failure)
        if PASS_TITLE in last_titles:
            return PASS_TITLE
        sleep(0.25)
    raise RuntimeError(f"Frontend/native panel qualification timed out. Last titles: {last_titles!r}")


def process_windows(pid: int) -> list[tuple[int, str]]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    rows: list[tuple[int, str]] = []
    def inspect(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            text = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
            user32.GetWindowTextW(hwnd, text, len(text))
            rows.append((hwnd, text.value))
        return True
    if not user32.EnumWindows(callback_type(inspect), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return rows


def close_process_windows(pid: int) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    for hwnd, _ in process_windows(pid):
        if not user32.PostMessageW(hwnd, 0x0010, 0, 0):  # WM_CLOSE through normal host recovery
            raise ctypes.WinError(ctypes.get_last_error())


def verify(desktop: Path, *, timeout: float = 45) -> dict:
    if os.name != "nt":
        raise RuntimeError("This acceptance check requires Windows.")
    if not desktop.is_file():
        raise RuntimeError(f"Desktop executable is missing: {desktop}")
    try:
        connection = socket.create_connection(("127.0.0.1", 1420), timeout=0.5)
    except OSError:
        pass
    else:
        connection.close()
        raise RuntimeError("Stop the development frontend on port 1420 before checking embedded assets.")
    with tempfile.TemporaryDirectory(prefix="spike-frontend-proof-", ignore_cleanup_errors=True) as profile:
        environment = {**os.environ, "WEBVIEW2_USER_DATA_FOLDER": profile}
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen([str(desktop.resolve()), "--panel-popup-qualification"],
                                       env=environment, stdout=log, stderr=log, startupinfo=startup)
            try:
                title = await_qualification(process, lambda: [title for _, title in process_windows(process.pid)], timeout=timeout)
                close_process_windows(process.pid)
                try:
                    code = process.wait(timeout=10)
                except subprocess.TimeoutExpired as error:
                    raise RuntimeError("Qualified frontend did not close through the normal window close protocol.") from error
                if code != 0:
                    raise RuntimeError(f"Desktop closed with exit code {code}.")
                return {"status": "PASS", "frontend": "embedded", "native_panel_lifecycle": title,
                        "normal_close": "passed", "profile": "disposable", "production_qualified": False}
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desktop", type=Path)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be from 1 to 120 seconds")
    try:
        report = verify(args.desktop, timeout=args.timeout)
    except (OSError, RuntimeError) as error:
        report = {"status": "FAIL", "error": str(error), "production_qualified": False}
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
