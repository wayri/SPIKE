# SPDX-License-Identifier: Apache-2.0
"""Explicit package qualification profiles; supervisor defaults stay strict."""
from __future__ import annotations


def release_supervision_profile(platform: str) -> dict:
    if platform == "darwin":
        return {
            "resource_policy": "darwin_sampled_rss",
            "enforcement": "darwin_process_group_sampled_rss_experimental",
            "validation_state": "experimental",
            "hard_memory_cap": False,
            "memory_metric": "sum_process_group_rss",
            "memory_limit_mib": 4096,
            "sample_interval_seconds": 0.05,
            "observer_timeout_seconds": 0.5,
            "limits": [
                "Sampled resident memory can exceed the budget between observations.",
                "Shared resident pages can be counted more than once.",
                "Process groups do not contain descendants that create another session.",
                "Monitoring ends at leader exit; remaining descendants are not covered.",
                "This profile qualifies the dedicated circuit-worker probe, not all app processes.",
            ],
        }
    if platform in {"linux", "win32"}:
        return {
            "resource_policy": "strict_address_space",
            "enforcement": ("windows_job_object" if platform == "win32"
                            else "posix_process_group_rlimit"),
            "validation_state": "experimental",
            "hard_memory_cap": True,
            "memory_metric": "job_memory" if platform == "win32" else "address_space",
            "memory_limit_mib": 4096,
        }
    raise ValueError("Unsupported release supervision platform")
