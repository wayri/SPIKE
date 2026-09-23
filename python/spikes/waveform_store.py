"""Recoverable, chunked, bounded waveform storage for SPIKES.

Chunks are independently decodable and CRC protected.  The default
``xor-zlib`` codec losslessly XOR-predicts IEEE-754 bit patterns per channel
before compression; it never quantizes simulation values.
"""

from __future__ import annotations

import json
import lzma
import os
from array import array
from dataclasses import dataclass
from pathlib import Path
import struct
import sys
from typing import Any, Iterable, Iterator, Mapping, Sequence
import zlib

from .streaming_contracts import UniformStreamSchema, normalized_frame


WAVEFORM_FILE_CONTRACT = "spikes/chunked-waveform/v1"
MAGIC = b"SPKWF1\r\n"
CHUNK_MARKER = b"CHNK"
DONE_MARKER = b"DONE"
HEADER_PREFIX = struct.Struct("<8sI")
CHUNK_HEADER = struct.Struct("<4sQQIII")
MAX_HEADER_BYTES = 1_048_576
MAX_CHUNK_RAW_BYTES = 256 * 1024 * 1024
MAX_CHUNK_PAYLOAD_BYTES = MAX_CHUNK_RAW_BYTES + 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 512 * 1024 * 1024
SUPPORTED_CODECS = ("none", "zlib-fast", "zlib", "xor-zlib", "lzma")


class WaveformStoreError(RuntimeError):
    pass


class WaveformSizeLimitError(WaveformStoreError):
    pass


@dataclass(frozen=True, slots=True)
class WaveformChunk:
    first_sample_index: int
    frames: tuple[tuple[float, ...], ...]

    @property
    def sample_count(self) -> int:
        return len(self.frames)


def _pack_frames(
    frames: Sequence[Sequence[float]], channel_count: int
) -> tuple[bytes, tuple[tuple[float, ...], ...]]:
    normalized = tuple(normalized_frame(frame, channel_count) for frame in frames)
    if not normalized:
        raise ValueError("waveform chunks cannot be empty.")
    raw_bytes = len(normalized) * channel_count * 8
    if raw_bytes > MAX_CHUNK_RAW_BYTES:
        raise ValueError(f"raw waveform chunk exceeds {MAX_CHUNK_RAW_BYTES} bytes.")
    values = array("d")
    for frame in normalized:
        values.extend(frame)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes(), normalized


def _unpack_frames(raw: bytes, channel_count: int, sample_count: int) -> tuple[tuple[float, ...], ...]:
    expected = channel_count * sample_count * 8
    if len(raw) != expected:
        raise WaveformStoreError("decoded waveform byte count does not match chunk metadata.")
    values = array("d")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    return tuple(
        tuple(values[offset : offset + channel_count])
        for offset in range(0, len(values), channel_count)
    )


def _xor_transform(raw: bytes, channel_count: int) -> bytes:
    words = array("Q")
    words.frombytes(raw)
    if sys.byteorder != "little":
        words.byteswap()
    previous = [0] * channel_count
    for index in range(len(words)):
        channel = index % channel_count
        current = words[index]
        words[index] = current ^ previous[channel]
        previous[channel] = current
    if sys.byteorder != "little":
        words.byteswap()
    return words.tobytes()


def _xor_restore(encoded: bytes, channel_count: int) -> bytes:
    words = array("Q")
    words.frombytes(encoded)
    if sys.byteorder != "little":
        words.byteswap()
    previous = [0] * channel_count
    for index in range(len(words)):
        channel = index % channel_count
        current = words[index] ^ previous[channel]
        words[index] = current
        previous[channel] = current
    if sys.byteorder != "little":
        words.byteswap()
    return words.tobytes()


def _compress(raw: bytes, codec: str, channel_count: int) -> bytes:
    if codec == "none":
        return raw
    if codec == "zlib-fast":
        return zlib.compress(raw, level=1)
    if codec == "zlib":
        return zlib.compress(raw, level=6)
    if codec == "xor-zlib":
        return zlib.compress(_xor_transform(raw, channel_count), level=6)
    if codec == "lzma":
        return lzma.compress(raw, preset=0)
    raise ValueError(f"unsupported waveform codec {codec!r}.")


def _decompress(payload: bytes, codec: str, channel_count: int) -> bytes:
    try:
        if codec == "none":
            return payload
        if codec in {"zlib-fast", "zlib"}:
            return zlib.decompress(payload)
        if codec == "xor-zlib":
            return _xor_restore(zlib.decompress(payload), channel_count)
        if codec == "lzma":
            return lzma.decompress(payload)
    except (zlib.error, lzma.LZMAError, ValueError) as exc:
        raise WaveformStoreError(f"waveform chunk decompression failed: {exc}") from exc
    raise WaveformStoreError(f"unsupported waveform codec {codec!r}.")


class ChunkedWaveformWriter:
    """Append-only writer with a hard file-size admission limit."""

    def __init__(
        self,
        path: str | Path,
        schema: UniformStreamSchema,
        *,
        codec: str = "xor-zlib",
        max_chunk_samples: int = 4096,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        overwrite: bool = False,
    ) -> None:
        if codec not in SUPPORTED_CODECS:
            raise ValueError(f"codec must be one of {', '.join(SUPPORTED_CODECS)}.")
        if isinstance(max_chunk_samples, bool) or not isinstance(max_chunk_samples, int) or max_chunk_samples < 1:
            raise ValueError("max_chunk_samples must be a positive integer.")
        if max_chunk_samples * len(schema.channels) * 8 > MAX_CHUNK_RAW_BYTES:
            raise ValueError("configured chunk dimensions exceed the raw chunk byte bound.")
        if isinstance(max_file_bytes, bool) or not isinstance(max_file_bytes, int) or max_file_bytes < 4096:
            raise ValueError("max_file_bytes must be an integer of at least 4096.")
        self.path = Path(path)
        self.schema = schema
        self.codec = codec
        self.max_chunk_samples = max_chunk_samples
        self.max_file_bytes = max_file_bytes
        self._next_sample_index = 0
        self._closed = False
        mode = "wb" if overwrite else "xb"
        self._file = self.path.open(mode)
        header = json.dumps(
            {
                "contract": WAVEFORM_FILE_CONTRACT,
                "codec": codec,
                "schema": schema.to_dict(),
                "independently_decodable_chunks": True,
                "lossy": False,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(header) > MAX_HEADER_BYTES:
            self._file.close()
            raise ValueError("waveform header exceeds its byte bound.")
        prefix = HEADER_PREFIX.pack(MAGIC, len(header))
        if len(prefix) + len(header) + len(DONE_MARKER) > max_file_bytes:
            self._file.close()
            raise WaveformSizeLimitError("waveform header exceeds the configured file limit.")
        self._file.write(prefix)
        self._file.write(header)

    @property
    def bytes_written(self) -> int:
        return self._file.tell()

    def append(
        self,
        frames: Sequence[Sequence[float]],
        *,
        first_sample_index: int | None = None,
    ) -> None:
        if self._closed:
            raise WaveformStoreError("waveform writer is closed.")
        first = self._next_sample_index if first_sample_index is None else first_sample_index
        if isinstance(first, bool) or not isinstance(first, int) or first < self._next_sample_index:
            raise ValueError("first sample index must not overlap previously written chunks.")
        if not frames:
            raise ValueError("waveform append requires at least one frame.")
        offset = 0
        while offset < len(frames):
            batch = frames[offset : offset + self.max_chunk_samples]
            raw, normalized = _pack_frames(batch, len(self.schema.channels))
            payload = _compress(raw, self.codec, len(self.schema.channels))
            chunk_first = first + offset
            header = CHUNK_HEADER.pack(
                CHUNK_MARKER,
                chunk_first,
                len(normalized),
                len(raw),
                len(payload),
                zlib.crc32(raw),
            )
            required = len(header) + len(payload) + len(DONE_MARKER)
            if self._file.tell() + required > self.max_file_bytes:
                raise WaveformSizeLimitError(
                    "next waveform chunk would exceed the configured file-size limit."
                )
            self._file.write(header)
            self._file.write(payload)
            offset += len(normalized)
        self._next_sample_index = first + len(frames)

    def flush(self, *, durable: bool = False) -> None:
        self._file.flush()
        if durable:
            os.fsync(self._file.fileno())

    def close(self, *, complete: bool = True) -> None:
        if self._closed:
            return
        if complete and self._file.tell() + len(DONE_MARKER) <= self.max_file_bytes:
            self._file.write(DONE_MARKER)
        self._file.flush()
        self._file.close()
        self._closed = True

    def __enter__(self) -> "ChunkedWaveformWriter":
        return self

    def __exit__(self, exception_type: Any, *_: Any) -> None:
        self.close(complete=exception_type is None)

    def __del__(self) -> None:
        try:
            self.close(complete=False)
        except Exception:
            pass


class ChunkedWaveformReader:
    """Streaming reader that recovers every complete chunk before a torn tail."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._file = self.path.open("rb")
        prefix = self._file.read(HEADER_PREFIX.size)
        if len(prefix) != HEADER_PREFIX.size:
            self._file.close()
            raise WaveformStoreError("waveform file header is truncated.")
        magic, header_length = HEADER_PREFIX.unpack(prefix)
        if magic != MAGIC or header_length > MAX_HEADER_BYTES:
            self._file.close()
            raise WaveformStoreError("waveform file magic or header length is invalid.")
        raw_header = self._file.read(header_length)
        if len(raw_header) != header_length:
            self._file.close()
            raise WaveformStoreError("waveform JSON header is truncated.")
        try:
            header = json.loads(raw_header)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._file.close()
            raise WaveformStoreError("waveform JSON header is invalid.") from exc
        if not isinstance(header, Mapping):
            self._file.close()
            raise WaveformStoreError("waveform JSON header must be an object.")
        if header.get("contract") != WAVEFORM_FILE_CONTRACT:
            self._file.close()
            raise WaveformStoreError("waveform file contract is unsupported.")
        self.codec = str(header.get("codec", ""))
        if self.codec not in SUPPORTED_CODECS:
            self._file.close()
            raise WaveformStoreError("waveform file codec is unsupported.")
        schema_value = header.get("schema")
        if not isinstance(schema_value, Mapping):
            self._file.close()
            raise WaveformStoreError("waveform schema is missing.")
        self.schema = UniformStreamSchema.from_dict(schema_value)
        self._data_offset = self._file.tell()
        self.complete = False
        self.issues: list[str] = []

    def iter_chunks(self) -> Iterator[WaveformChunk]:
        self._file.seek(self._data_offset)
        self.complete = False
        self.issues.clear()
        while True:
            marker = self._file.read(4)
            if marker == DONE_MARKER:
                self.complete = True
                return
            if not marker:
                self.issues.append("missing completion marker; recovered complete chunks only")
                return
            if marker != CHUNK_MARKER:
                self.issues.append("invalid or torn chunk marker; recovered preceding chunks")
                return
            remainder = self._file.read(CHUNK_HEADER.size - 4)
            if len(remainder) != CHUNK_HEADER.size - 4:
                self.issues.append("truncated chunk header; recovered preceding chunks")
                return
            _, first_index, sample_count, raw_length, payload_length, expected_crc = CHUNK_HEADER.unpack(
                marker + remainder
            )
            expected_raw = sample_count * len(self.schema.channels) * 8
            if not sample_count or raw_length != expected_raw or raw_length > MAX_CHUNK_RAW_BYTES:
                raise WaveformStoreError("waveform chunk dimensions are invalid.")
            if payload_length > MAX_CHUNK_PAYLOAD_BYTES:
                raise WaveformStoreError("waveform compressed chunk exceeds its byte bound.")
            payload = self._file.read(payload_length)
            if len(payload) != payload_length:
                self.issues.append("truncated chunk payload; recovered preceding chunks")
                return
            raw = _decompress(payload, self.codec, len(self.schema.channels))
            if len(raw) != raw_length or zlib.crc32(raw) != expected_crc:
                raise WaveformStoreError("waveform chunk length or CRC validation failed.")
            yield WaveformChunk(
                first_sample_index=first_index,
                frames=_unpack_frames(raw, len(self.schema.channels), sample_count),
            )

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "ChunkedWaveformReader":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def compare_codecs(
    schema: UniformStreamSchema,
    frames: Sequence[Sequence[float]],
) -> dict[str, Any]:
    """Return deterministic size evidence; CPU timing is intentionally excluded."""

    raw, _ = _pack_frames(frames, len(schema.channels))
    trials = []
    for codec in SUPPORTED_CODECS:
        payload = _compress(raw, codec, len(schema.channels))
        trials.append({
            "codec": codec,
            "raw_bytes": len(raw),
            "stored_bytes": len(payload),
            "compression_ratio": len(raw) / max(1, len(payload)),
            "lossy": False,
        })
    best = min(trials, key=lambda item: (item["stored_bytes"], item["codec"]))
    return {
        "contract": "spikes/waveform-compression-comparison/v1",
        "sample_count": len(frames),
        "channel_count": len(schema.channels),
        "recommended_for_size": best["codec"],
        "trials": trials,
        "note": "Size-only comparison; qualify throughput separately on target hardware.",
    }


__all__ = [
    "DEFAULT_MAX_FILE_BYTES", "SUPPORTED_CODECS", "WAVEFORM_FILE_CONTRACT",
    "ChunkedWaveformReader", "ChunkedWaveformWriter", "WaveformChunk",
    "WaveformSizeLimitError", "WaveformStoreError", "compare_codecs",
]
