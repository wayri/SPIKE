"""Deterministic spatial result-admission utilities.

This stable module boundary is used by solver result and preview paths.  The
implementation remains shared with the established DC result utilities while
callers stay independent of any one solver family.
"""

from .dc_result_utils import stratified_sample_records

__all__ = ["stratified_sample_records"]
