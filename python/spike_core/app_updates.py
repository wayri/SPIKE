# SPDX-License-Identifier: Apache-2.0
"""Official stable release discovery and bounded download; never executes files."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import urlsplit, unquote
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.github.com/repos/wayri/spike/releases/latest"
CONTRACT = "spike/app-update/v1"
MAX_SIZE = 4 * 1024**3
MARKER = "SPIKE-owned-update-cache-v1\n"


def version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        raise ValueError("A stable three-part SPIKE version is required.")
    return tuple(map(int, match.groups()))


def validate_url(url, *, api=False, redirect=False):
    p = urlsplit(url)
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443) or p.fragment:
        raise ValueError("Update transport requires an approved HTTPS URL.")
    if api and url == API:
        return url
    path = unquote(p.path)
    if "\\" in path or any(x in (".", "..") for x in path.split("/")):
        raise ValueError("Invalid release asset path.")
    if p.hostname == "github.com" and path.lower().startswith("/wayri/spike/releases/download/") and not p.query:
        return url
    if redirect and p.hostname == "release-assets.githubusercontent.com" and path.startswith("/github-production-release-asset/"):
        return url
    raise ValueError("Update URL is outside the official release transport.")


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, redirect=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url, *, api=False):
    validate_url(url, api=api)
    return build_opener(SafeRedirect()).open(Request(url, headers={
        "User-Agent": "SPIKE-desktop-updater", "Accept": "application/vnd.github+json" if api else "application/octet-stream",
    }), timeout=20)


def safe_path(path):
    """Reject symlinks and Windows junction/reparse ancestors, including the leaf."""
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Update cache must not contain symlinks or reparse points.")
    return path


def cache_root():
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise ValueError("Windows local application data is unavailable.")
    root = safe_path(Path(base) / "SPIKE" / "updates" / "v1")
    if not root.exists():
        root.mkdir(parents=True)
        (root / "owner.txt").write_bytes(MARKER.encode("ascii"))
    marker = safe_path(root / "owner.txt")
    if not marker.is_file() or marker.stat().st_size != len(MARKER) or marker.read_text(encoding="ascii") != MARKER:
        raise ValueError("Refusing an unrecognized update cache.")
    return root


def select_release(release, current_version, system, machine):
    installed = re.fullmatch(r"v?(\d+\.\d+\.\d+)(?:-([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*))?", str(current_version))
    if installed is None:
        raise ValueError("The installed SPIKE version is malformed.")
    current = version(installed[1])
    current_is_prerelease = installed[2] is not None
    latest = version(release.get("tag_name"))
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Only published stable releases can be installed.")
    result = {"contract": CONTRACT, "current_version": current_version,
              "latest_version": str(release["tag_name"]).removeprefix("v"),
              "release_url": "https://github.com/wayri/spike/releases/latest",
              "status": "current", "received_bytes": 0, "total_bytes": 0}
    if latest < current or (latest == current and not current_is_prerelease):
        result["message"] = "This SPIKE version is current or newer than the stable release."
        return result
    arch = {"x86_64": "x64", "aarch64": "arm64"}.get(machine)
    if system != "windows" or not arch:
        return {**result, "status": "unsupported", "message": "Automatic installation is available for Windows x64/ARM64 setup releases only."}
    # Tauri NSIS names: SPIKE_0.3.9_x64-setup.exe. Reject portable/source assets.
    pattern = re.compile(r"SPIKE_" + re.escape(result["latest_version"]) + "_" + arch + r"-setup\.exe", re.I)
    assets = [a for a in release.get("assets", []) if isinstance(a, dict) and pattern.fullmatch(str(a.get("name", "")))]
    if len(assets) != 1:
        return {**result, "status": "unsupported", "message": "The stable release has no unique matching Windows setup asset."}
    asset = assets[0]
    digest = str(asset.get("digest", ""))
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
        return {**result, "status": "unsupported", "message": "GitHub has not published a SHA-256 digest for this installer. Installation is unavailable."}
    size = asset.get("size")
    if type(size) is not int or not 0 < size <= MAX_SIZE:
        raise ValueError("Installer size is outside the 4 GiB safety limit.")
    url = validate_url(str(asset.get("browser_download_url", "")))
    return {**result, "status": "available", "asset_name": asset["name"], "size": size,
            "total_bytes": size, "unattended_supported": True, "sha256": digest[7:].lower(), "download_url": url,
            "message": "A verified-download stable update is available."}


def check(params):
    with open_url(API, api=True) as response:
        data = response.read(2 * 1024**2 + 1)
    if len(data) > 2 * 1024**2:
        raise ValueError("Release metadata exceeds the 2 MiB limit.")
    return select_release(json.loads(data), params["current_version"], params["platform"], params["machine"])


def download(params, progress):
    # Refetch authoritative metadata; never accept executable URLs/hashes from UI.
    result = check(params)
    if result["status"] != "available":
        raise ValueError(result["message"])
    if result["latest_version"] != params.get("latest_version"):
        raise ValueError("The latest release changed. Check again before downloading.")
    root = cache_root()
    partial = safe_path(root / "setup.partial")
    final = safe_path(root / "setup.exe")
    if partial.exists() or final.exists():
        raise ValueError("An earlier installer remains in the cache; use Check again to clean it safely.")
    started, received, digest = time.monotonic(), 0, hashlib.sha256()
    try:
        with partial.open("xb") as out, open_url(result["download_url"]) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != result["size"]:
                raise ValueError("Installer Content-Length does not match release metadata.")
            while True:
                if time.monotonic() - started > 1800:
                    raise TimeoutError("Installer download exceeded 30 minutes.")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > result["size"]:
                    raise ValueError("Installer is larger than the release asset.")
                out.write(chunk)
                digest.update(chunk)
                progress({"received_bytes": received, "total_bytes": result["size"]})
            out.flush()
            os.fsync(out.fileno())
        if received != result["size"] or digest.hexdigest() != result["sha256"]:
            raise ValueError("Installer size or SHA-256 verification failed.")
        safe_path(final)
        os.replace(partial, final)
    except BaseException:
        safe_path(partial).unlink(missing_ok=True)
        raise
    return {**result, "status": "ready", "received_bytes": received,
            "message": "Installer downloaded and SHA-256 verified. Save and close all work before installing."}


def handle_app_update(method, params, request_id):
    from .worker_progress import emit_worker_progress
    operation = check if method == "app_update_check" else lambda p: download(
        p, lambda frame: emit_worker_progress(str(request_id), method, frame))
    return {"ok": True, "result": operation(params)}
