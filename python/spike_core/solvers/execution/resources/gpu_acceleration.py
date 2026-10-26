"""Optional CUDA sparse solve, with FP64 data and an original-system residual.

CuPy is discovered locally; this adapter never downloads a runtime. GPU driver,
allocation and validation failures may fall back only under automatic policy.
"""
from __future__ import annotations
import importlib.util
from functools import lru_cache
from typing import Any
import numpy as np
from scipy.sparse import csr_matrix


@lru_cache(maxsize=1)
def cuda_status() -> tuple[bool, str, str]:
    try:
        if importlib.util.find_spec("cupy") is None:
            return False, "", "CuPy/CUDA is not installed in the worker runtime."
        import cupy as cp
        if cp.cuda.runtime.is_hip:
            return False, cp.__version__, "This sparse adapter requires NVIDIA CUDA."
        if cp.cuda.runtime.getDeviceCount() < 1:
            return False, cp.__version__, "No CUDA device is available."
        return True, cp.__version__, ""
    except Exception as exc:
        return False, "", f"CUDA discovery failed: {exc}"


def checked_solution(matrix: Any, rhs: np.ndarray, solution: np.ndarray, tolerance: float = 1e-9) -> float:
    source = csr_matrix(matrix)
    right = np.asarray(rhs)
    value = np.asarray(solution)
    if value.shape != right.shape or not np.all(np.isfinite(value)):
        raise RuntimeError("GPU solver returned an invalid shape or non-finite solution.")
    residual = np.asarray(source @ value - right)
    # Componentwise backward error also handles zero RHS and badly scaled nets.
    scale = np.asarray(abs(source) @ np.abs(value)) + np.abs(right)
    if not np.all(np.isfinite(residual)) or not np.all(np.isfinite(scale)):
        raise RuntimeError("GPU residual validation overflowed; solution cannot be verified.")
    error = float(np.max(np.abs(residual) / np.maximum(scale, np.finfo(float).tiny), initial=0))
    if not np.isfinite(error) or error > tolerance:
        raise RuntimeError(f"GPU solution failed original-system residual validation ({error:g}).")
    return error


def solve_cuda(matrix: Any, rhs: np.ndarray) -> np.ndarray:
    import cupy as cp
    from cupyx.scipy.sparse import csr_matrix as gpu_csr
    from cupyx.scipy.sparse.linalg import spsolve
    dtype = np.complex128 if np.iscomplexobj(matrix.data) or np.iscomplexobj(rhs) else np.float64
    source = csr_matrix(matrix, dtype=dtype, copy=True)
    source.sum_duplicates(); source.sort_indices()
    right = np.asarray(rhs, dtype=dtype)
    if source.shape[0] != source.shape[1] or right.ndim not in (1, 2) or right.shape[0] != source.shape[0]:
        raise ValueError("GPU solve requires a square matrix and compatible RHS.")
    if max(source.shape, default=0) >= 2**31 or source.nnz >= 2**31:
        raise ValueError("CUDA sparse QR requires 32-bit sparse indexes.")
    if not np.all(np.isfinite(source.data)) or not np.all(np.isfinite(right)):
        raise ValueError("GPU solve requires finite matrix and RHS values.")
    free, _ = cp.cuda.runtime.memGetInfo()
    # Factorization fill-in can exceed this estimate; allocator failures are
    # caught by the caller's explicit/automatic policy, never by downsampling.
    required = (source.data.nbytes + source.indices.nbytes + source.indptr.nbytes + right.nbytes) * 8
    if required > free * .6:
        raise MemoryError("Insufficient free GPU memory for the sparse solve working-set estimate.")
    # A private pool releases this operation's idle allocations without touching
    # other device users. Do not silently demote double precision to float32.
    pool = cp.cuda.MemoryPool()
    with cp.cuda.using_allocator(pool.malloc):
        device_matrix = device_rhs = device_solution = None
        try:
            device_matrix = gpu_csr((cp.asarray(source.data), cp.asarray(source.indices, dtype=cp.int32),
                                    cp.asarray(source.indptr, dtype=cp.int32)), shape=source.shape)
            device_rhs = cp.asarray(right)
            device_solution = spsolve(device_matrix, device_rhs)
            result = cp.asnumpy(device_solution)
            checked_solution(source, right, result)
            return result
        finally:
            device_solution = device_rhs = device_matrix = None
            pool.free_all_blocks()
