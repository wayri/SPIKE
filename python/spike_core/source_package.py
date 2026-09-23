"""Bounded, deterministic source packages. Never extract an archive onto disk."""
from __future__ import annotations

import gzip
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import time
import zipfile

from .importers import ImportPolicy


def safe_member_name(name: str) -> str:
    if not name or "\\" in name or ":" in name or "\x00" in name or name.startswith("/"):
        raise ValueError(f"Unsafe source member: {name!r}")
    parts = PurePosixPath(name).parts
    if ".." in parts or any(part.endswith((" ", ".")) for part in parts):
        raise ValueError(f"Unsafe source member: {name!r}")
    return str(PurePosixPath(*parts))


class SourcePackage:
    """Read directory, zip, tar and gzip-tar jobs under the same resource policy.

    Members are indexed before parsing. Links, devices, duplicate/case-colliding
    names and ambiguous roots are rejected; compressed inner files are bounded
    again when read. No source paths or archive entries are executed.
    """

    def __init__(self, path: str | Path, policy: ImportPolicy | None = None):
        self.path = Path(path)
        self.policy = policy or ImportPolicy()
        self.deadline = time.monotonic() + self.policy.timeout_seconds
        self.members: dict[str, object] = {}
        self.sizes: dict[str, int] = {}
        self.archive = None
        self.expanded = 0
        self.read_bytes = 0
        self._seen: set[str] = set()
        try:
            if self.path.is_symlink() or (hasattr(self.path, "is_junction") and self.path.is_junction()):
                raise ValueError("Source package cannot be a symbolic link or junction.")
            if self.path.is_dir():
                root = self.path.resolve()
                for directory, dirs, files in os.walk(root, followlinks=False):
                    self.check_time()
                    for name in dirs + files:
                        entry = Path(directory) / name
                        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                            raise ValueError("Links and junctions are forbidden in source packages.")
                        if not entry.resolve().is_relative_to(root):
                            raise ValueError("Source member escapes package root.")
                        self._add(entry.relative_to(root).as_posix(), entry, entry.stat().st_size if entry.is_file() else 0, entry.is_dir())
            elif self.path.is_file():
                size = self.path.stat().st_size
                if size > self.policy.max_source_bytes:
                    raise ValueError("Source archive exceeds source byte limit.")
                if zipfile.is_zipfile(self.path):
                    self.archive = zipfile.ZipFile(self.path)
                    for entry in self.archive.infolist():
                        safe_member_name(entry.orig_filename.rstrip("/"))
                        mode = entry.external_attr >> 16
                        if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.flag_bits & 1:
                            raise ValueError("Encrypted or non-regular archive members are forbidden.")
                        if entry.file_size > max(1, entry.compress_size) * self.policy.max_compression_ratio:
                            raise ValueError("Source member exceeds compression ratio limit.")
                        self._add(entry.filename.rstrip("/"), entry, entry.file_size, entry.is_dir())
                else:
                    self.archive = tarfile.open(self.path, "r:*")
                    for entry in self.archive:
                        if not (entry.isfile() or entry.isdir()):
                            raise ValueError("Archive links, devices and special files are forbidden.")
                        self._add(entry.name.rstrip("/"), entry, entry.size, entry.isdir())
                if self.expanded > max(1, size) * self.policy.max_compression_ratio:
                    raise ValueError("Source package exceeds compression ratio limit.")
            else:
                raise FileNotFoundError(f"Source package does not exist: {self.path}")
        except BaseException:
            self.close()
            raise

    def check_time(self):
        if time.monotonic() > self.deadline:
            raise ValueError("Source package exceeded import deadline.")

    def _add(self, name, entry, size, directory=False):
        self.check_time()
        name = safe_member_name(name)
        key = name.casefold()
        if key in self._seen:
            raise ValueError(f"Duplicate or case-colliding source member: {name}")
        self._seen.add(key)
        if len(self._seen) > self.policy.max_archive_members:
            raise ValueError("Source package exceeds member count limit.")
        self.expanded += size
        if size < 0 or size > self.policy.max_source_bytes or self.expanded > self.policy.max_expanded_bytes:
            raise ValueError("Source package exceeds expanded byte limit.")
        if not directory:
            self.members[name] = entry
            self.sizes[name] = size

    def read(self, name: str) -> bytes:
        self.check_time()
        entry = self.members[name]
        if isinstance(entry, Path):
            if entry.is_symlink() or not entry.resolve().is_relative_to(self.path.resolve()):
                raise ValueError("Source member changed to an unsafe path.")
            stream = entry.open("rb")
        elif isinstance(self.archive, zipfile.ZipFile):
            stream = self.archive.open(entry)
        else:
            stream = self.archive.extractfile(entry)
        with stream:
            data = stream.read(min(self.policy.max_source_bytes, self.sizes[name]) + 1)
        if len(data) != self.sizes[name]:
            raise ValueError(f"Source member size changed: {name}")
        self.read_bytes += len(data)
        if self.read_bytes > self.policy.max_expanded_bytes:
            raise ValueError("Source reads exceed expanded byte limit.")
        return data

    def text(self, name: str, *, required=False) -> str:
        compressed = name + ".gz"
        if name in self.members and compressed in self.members:
            raise ValueError(f"Ambiguous plain/compressed source member: {name}")
        if name in self.members:
            data = self.read(name)
        elif compressed in self.members:
            if self.policy.max_archive_depth < 1:
                raise ValueError("Nested gzip members are disabled by policy.")
            raw = self.read(compressed)
            limit = min(self.policy.max_source_bytes, self.policy.max_expanded_bytes - self.read_bytes,
                        int(max(1, len(raw)) * self.policy.max_compression_ratio))
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError("Nested gzip member exceeds expanded byte or compression ratio limit.")
            self.read_bytes += len(data)
        elif name + ".Z" in self.members:
            raise ValueError(f"Unix compress (.Z) encoding is not supported for source member: {name}. Re-export with gzip or uncompressed members.")
        elif required:
            raise ValueError(f"Required source member is missing: {name}")
        else:
            return ""
        if b"\x00" in data:
            raise ValueError(f"NUL byte in source text: {name}")
        # ODB++ legacy property strings are byte strings; surrogateescape would
        # create invalid JSON. Latin-1 provides a reversible fallback.
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode("latin-1")

    def root_for(self, marker: str) -> str:
        roots = [name[:-len(marker)] for name in self.members
                 if name == marker or name.endswith("/" + marker)]
        if len(roots) != 1:
            raise ValueError(f"Expected one package root containing {marker}; found {len(roots)}.")
        return roots[0]

    def close(self):
        if self.archive is not None:
            self.archive.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def source_identity(path: Path, policy: ImportPolicy | None = None) -> tuple[str, int]:
    """Hash file bytes, or a sorted, length-delimited directory manifest."""
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest(), path.stat().st_size
    with SourcePackage(path, policy) as package:
        for name in sorted(package.members):
            encoded = name.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            digest.update(package.sizes[name].to_bytes(8, "big"))
            digest.update(hashlib.sha256(package.read(name)).digest())
        return digest.hexdigest(), package.expanded
