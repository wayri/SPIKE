# SPDX-License-Identifier: Apache-2.0
"""Resource bounds for reading SPIKE project packages."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PackageLimits:
    max_members: int = 100_000
    max_member_bytes: int = 2 * 1024 * 1024 * 1024
    max_total_bytes: int = 16 * 1024 * 1024 * 1024
    max_compression_ratio: float = 200.0
    max_path_depth: int = 12
    max_manifest_bytes: int = 16 * 1024 * 1024
    max_control_plane_json_bytes: int = 64 * 1024 * 1024
    max_design_ir_json_bytes: int = 512 * 1024 * 1024

    def __post_init__(self) -> None:
        if min(self.max_members, self.max_member_bytes, self.max_total_bytes,
               self.max_path_depth, self.max_manifest_bytes,
               self.max_control_plane_json_bytes, self.max_design_ir_json_bytes) <= 0:
            raise ValueError("Package limits must be positive.")
        if self.max_compression_ratio < 1.0:
            raise ValueError("Package compression ratio must be at least one.")
