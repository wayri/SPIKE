"""Optional numerical acceleration with deterministic, inspectable fallbacks.

Acceleration must not change the physical model or silently promote result
quality.  This module owns backend discovery, policy, sparse solves, and graph
matrix assembly so solver adapters can report exactly what executed.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import functools
import os
import platform
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Tuple

import numpy as np
from scipy.sparse import csc_matrix, csr_matrix, spmatrix
from scipy.sparse.linalg import splu


ACCELERATION_CONTRACT = "spike/acceleration-catalog/v1"
SPARSE_BACKENDS = {"auto", "scipy-superlu", "petsc-mumps"}
ASSEMBLY_BACKENDS = {"auto", "numpy", "numba"}


class AccelerationUnavailableError(RuntimeError):
    """Raised when an explicitly requested optional backend is unavailable."""


@dataclass(frozen=True)
class AccelerationBackend:
    id: str
    name: str
    kind: str
    state: str
    version: str
    provider: str
    capabilities: Tuple[str, ...]
    reason: str = ""
    license: str = ""
    platforms: Tuple[str, ...] = ("windows", "linux", "macos")

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = list(self.capabilities)
        value["platforms"] = list(self.platforms)
        return value


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        try:
            module = importlib.import_module(name)
        except (ImportError, ValueError):
            return ""
        return str(getattr(module, "__version__", ""))


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _environment_integer(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), minimum)
    except (TypeError, ValueError):
        return default


def _numba_status() -> tuple[bool, str, str]:
    if not _module_available("numba"):
        return False, "", "Numba is not installed in the SPIKE worker runtime."
    try:
        import numba  # type: ignore[import-not-found]

        return True, str(numba.__version__), ""
    except Exception as exc:
        return False, _package_version("numba"), f"Numba discovery failed: {exc}"


def _petsc_mumps_status() -> tuple[bool, str, str]:
    """Return PETSc/MUMPS readiness without making it a required import."""

    if not _module_available("petsc4py"):
        return False, "", "petsc4py is not installed in the SPIKE worker runtime."
    try:
        from petsc4py import PETSc  # type: ignore[import-not-found]

        version = ".".join(str(part) for part in PETSc.Sys.getVersion()[:3])
        if not PETSc.Sys.hasExternalPackage("mumps"):
            return False, version, "PETSc is installed without the MUMPS external package."
        return True, version, ""
    except Exception as exc:
        return False, _package_version("petsc4py"), f"PETSc/MUMPS discovery failed: {exc}"


def acceleration_catalog() -> Dict[str, Any]:
    mumps_ready, petsc_version, mumps_reason = _petsc_mumps_status()
    numba_ready, numba_version, numba_reason = _numba_status()
    mumps_capabilities = ["real_sparse", "multifrontal", "single_process_adapter"]
    if mumps_ready:
        from petsc4py import PETSc  # type: ignore[import-not-found]

        if np.dtype(PETSc.ScalarType).kind == "c":
            mumps_capabilities.append("complex_sparse")
    backends = [
        AccelerationBackend(
            id="numpy",
            name="NumPy vectorized assembly",
            kind="assembly",
            state="available",
            version=np.__version__,
            provider="NumPy",
            capabilities=("graph_laplacian_assembly", "vectorized_geometry_kernels"),
            license="BSD-3-Clause",
        ),
        AccelerationBackend(
            id="numba",
            name="Numba CPU JIT",
            kind="assembly",
            state="available" if numba_ready else "unavailable",
            version=numba_version,
            provider="Numba",
            capabilities=("graph_laplacian_assembly", "compiled_cpu_kernel", "persistent_jit_cache"),
            reason=numba_reason,
            license="BSD-2-Clause",
        ),
        AccelerationBackend(
            id="scipy-superlu",
            name="SciPy SuperLU",
            kind="sparse_direct",
            state="available",
            version=_package_version("scipy"),
            provider="SciPy / SuperLU",
            capabilities=("real_sparse", "complex_sparse", "single_process", "pivoting"),
            license="BSD-3-Clause / BSD-style",
        ),
        AccelerationBackend(
            id="petsc-mumps",
            name="PETSc MUMPS",
            kind="sparse_direct",
            state="available" if mumps_ready else "unavailable",
            version=petsc_version,
            provider="PETSc / MUMPS",
            capabilities=tuple(mumps_capabilities),
            reason=mumps_reason,
            license="PETSc: BSD-2-Clause; MUMPS: CeCILL-C",
            platforms=("linux", "macos", "windows"),
        ),
    ]
    return {
        "contract": ACCELERATION_CONTRACT,
        "policy": {
            "sparse_backend": os.environ.get("SPIKE_SPARSE_BACKEND", "auto"),
            "assembly_backend": os.environ.get("SPIKE_ASSEMBLY_BACKEND", "auto"),
            "mumps_auto_min_unknowns": _environment_integer("SPIKE_MUMPS_MIN_UNKNOWNS", 100000),
            "numba_auto_min_branches": _environment_integer("SPIKE_NUMBA_MIN_BRANCHES", 50000),
            "offline": True,
            "downloads": "never_implicit",
        },
        "runtime": {
            "platform": {"darwin": "macos"}.get(platform.system().lower(), platform.system().lower()),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count() or 1,
        },
        "backends": [backend.to_dict() for backend in backends],
    }


def _available_backend(backend_id: str) -> bool:
    return any(
        backend["id"] == backend_id and backend["state"] == "available"
        for backend in acceleration_catalog()["backends"]
    )


def _backend_supports(backend_id: str, capability: str) -> bool:
    return any(
        backend["id"] == backend_id
        and backend["state"] == "available"
        and capability in backend.get("capabilities", [])
        for backend in acceleration_catalog()["backends"]
    )


def choose_sparse_backend(
    unknowns: int,
    nnz: int,
    *,
    requested: str = "auto",
    complex_values: bool = False,
) -> Dict[str, Any]:
    requested = str(requested or os.environ.get("SPIKE_SPARSE_BACKEND", "auto")).lower()
    if requested not in SPARSE_BACKENDS:
        raise ValueError(f"Unsupported sparse backend: {requested}")
    estimated_csr_bytes = int(max(nnz, 0) * (24 if complex_values else 16) + (max(unknowns, 0) + 1) * 8)
    mumps_threshold = _environment_integer("SPIKE_MUMPS_MIN_UNKNOWNS", 100000)
    if requested == "auto":
        mumps_compatible = _available_backend("petsc-mumps") and (
            not complex_values or _backend_supports("petsc-mumps", "complex_sparse")
        )
        if unknowns >= mumps_threshold and mumps_compatible:
            selected = "petsc-mumps"
            reason = f"MUMPS selected for {unknowns} unknowns at or above the {mumps_threshold} threshold."
        else:
            selected = "scipy-superlu"
            reason = (
                f"SuperLU selected for {unknowns} unknowns; PETSc/MUMPS is unavailable or below the "
                f"{mumps_threshold} auto-selection threshold."
            )
    else:
        selected = requested
        if not _available_backend(selected):
            raise AccelerationUnavailableError(f"Requested sparse backend is unavailable: {selected}")
        if selected == "petsc-mumps" and complex_values and not _backend_supports(selected, "complex_sparse"):
            raise AccelerationUnavailableError("The requested PETSc/MUMPS runtime does not support complex scalars.")
        reason = f"{selected} was selected explicitly."
    return {
        "requested": requested,
        "selected": selected,
        "selection_reason": reason,
        "unknowns": int(unknowns),
        "nnz": int(nnz),
        "complex_values": bool(complex_values),
        "estimated_csr_bytes": estimated_csr_bytes,
    }


def _solve_superlu(matrix: spmatrix, rhs: np.ndarray) -> np.ndarray:
    output_dtype = np.result_type(matrix.dtype, np.asarray(rhs).dtype)
    if output_dtype.kind not in {"f", "c"}:
        output_dtype = np.dtype(np.float64)
    source = csc_matrix(matrix, dtype=output_dtype)
    right = np.asarray(rhs, dtype=output_dtype)
    factor = splu(source, permc_spec="COLAMD")
    return np.asarray(factor.solve(right), dtype=output_dtype)


def _solve_petsc_mumps(matrix: spmatrix, rhs: np.ndarray) -> np.ndarray:
    from petsc4py import PETSc  # type: ignore[import-not-found]

    source = csr_matrix(matrix)
    output_dtype = np.result_type(source.dtype, np.asarray(rhs).dtype)
    if output_dtype.kind not in {"f", "c"}:
        output_dtype = np.dtype(np.float64)
    scalar_type = np.dtype(PETSc.ScalarType)
    if output_dtype.kind == "c" and scalar_type.kind != "c":
        raise AccelerationUnavailableError("This PETSc runtime was not built with complex scalar support.")
    if not np.can_cast(output_dtype, scalar_type, casting="safe"):
        raise AccelerationUnavailableError(
            f"The PETSc scalar type {scalar_type} cannot safely represent requested dtype {output_dtype}."
        )
    promoted = csr_matrix(source, dtype=output_dtype)
    values = np.asarray(promoted.data, dtype=scalar_type)
    indices = np.asarray(source.indices, dtype=PETSc.IntType)
    indptr = np.asarray(source.indptr, dtype=PETSc.IntType)
    petsc_matrix = right = solution = ksp = None
    try:
        petsc_matrix = PETSc.Mat().createAIJ(size=source.shape, csr=(indptr, indices, values), comm=PETSc.COMM_SELF)
        petsc_matrix.assemble()
        right_values = np.asarray(rhs, dtype=output_dtype).astype(scalar_type, copy=False)
        right = PETSc.Vec().createWithArray(right_values, comm=PETSc.COMM_SELF)
        solution = petsc_matrix.createVecRight()
        ksp = PETSc.KSP().create(comm=PETSc.COMM_SELF)
        ksp.setOperators(petsc_matrix)
        ksp.setType(PETSc.KSP.Type.PREONLY)
        preconditioner = ksp.getPC()
        preconditioner.setType(PETSc.PC.Type.LU)
        preconditioner.setFactorSolverType("mumps")
        ksp.solve(right, solution)
        reason = int(ksp.getConvergedReason())
        if reason <= 0:
            raise RuntimeError(f"PETSc/MUMPS failed with KSP converged reason {reason}.")
        result = solution.getArray(readonly=True).copy()
        return np.asarray(result, dtype=output_dtype)
    finally:
        for resource in (ksp, solution, right, petsc_matrix):
            if resource is not None:
                resource.destroy()


def solve_sparse_system(
    matrix: spmatrix,
    rhs: np.ndarray,
    *,
    requested: str = "auto",
) -> tuple[np.ndarray, Dict[str, Any]]:
    """Solve a sparse system and return execution metadata with any fallback."""

    source = csr_matrix(matrix)
    policy = choose_sparse_backend(
        source.shape[0],
        source.nnz,
        requested=requested,
        complex_values=bool(np.iscomplexobj(source.data) or np.iscomplexobj(rhs)),
    )
    selected = policy["selected"]
    fallback = ""
    if selected == "petsc-mumps":
        try:
            solution = _solve_petsc_mumps(source, rhs)
        except (AccelerationUnavailableError, ImportError, OSError) as exc:
            if policy["requested"] != "auto":
                raise AccelerationUnavailableError(str(exc)) from exc
            selected = "scipy-superlu"
            fallback = f"PETSc/MUMPS could not initialize; SuperLU fallback used: {exc}"
            solution = _solve_superlu(source, rhs)
    else:
        solution = _solve_superlu(source, rhs)
    return solution, {
        **policy,
        "selected": selected,
        "fallback": fallback,
        "fallback_used": bool(fallback),
    }


def choose_assembly_backend(branches: int, requested: str = "auto") -> Dict[str, Any]:
    requested = str(requested or os.environ.get("SPIKE_ASSEMBLY_BACKEND", "auto")).lower()
    if requested not in ASSEMBLY_BACKENDS:
        raise ValueError(f"Unsupported assembly backend: {requested}")
    threshold = _environment_integer("SPIKE_NUMBA_MIN_BRANCHES", 50000)
    if requested == "auto":
        selected = "numba" if branches >= threshold and _available_backend("numba") else "numpy"
        reason = (
            f"Numba selected for {branches} branches at or above the {threshold} threshold."
            if selected == "numba"
            else f"NumPy selected for {branches} branches; Numba is unavailable or below the {threshold} threshold."
        )
    else:
        selected = requested
        if selected == "numba" and not _available_backend("numba"):
            raise AccelerationUnavailableError("Requested assembly backend is unavailable: numba")
        reason = f"{selected} was selected explicitly."
    return {"requested": requested, "selected": selected, "selection_reason": reason, "branches": int(branches)}


def _numpy_laplacian_triplets(
    node_p: np.ndarray,
    node_n: np.ndarray,
    conductance: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    count = len(conductance)
    rows = np.empty(count * 4, dtype=np.int64)
    columns = np.empty(count * 4, dtype=np.int64)
    values = np.empty(count * 4, dtype=np.float64)
    rows[0::4], rows[1::4], rows[2::4], rows[3::4] = node_p, node_n, node_p, node_n
    columns[0::4], columns[1::4], columns[2::4], columns[3::4] = node_p, node_n, node_n, node_p
    values[0::4], values[1::4], values[2::4], values[3::4] = conductance, conductance, -conductance, -conductance
    return rows, columns, values


def _laplacian_triplet_loop(
    node_p: np.ndarray,
    node_n: np.ndarray,
    conductance: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    count = conductance.shape[0]
    rows = np.empty(count * 4, dtype=np.int64)
    columns = np.empty(count * 4, dtype=np.int64)
    values = np.empty(count * 4, dtype=np.float64)
    for index in range(count):
        offset = index * 4
        rows[offset] = node_p[index]
        rows[offset + 1] = node_n[index]
        rows[offset + 2] = node_p[index]
        rows[offset + 3] = node_n[index]
        columns[offset] = node_p[index]
        columns[offset + 1] = node_n[index]
        columns[offset + 2] = node_n[index]
        columns[offset + 3] = node_p[index]
        values[offset] = conductance[index]
        values[offset + 1] = conductance[index]
        values[offset + 2] = -conductance[index]
        values[offset + 3] = -conductance[index]
    return rows, columns, values


@functools.lru_cache(maxsize=1)
def _numba_laplacian_kernel() -> Any:
    from numba import njit  # type: ignore[import-not-found]

    return njit(cache=True)(_laplacian_triplet_loop)


def _numba_laplacian_triplets(
    node_p: np.ndarray,
    node_n: np.ndarray,
    conductance: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return _numba_laplacian_kernel()(node_p, node_n, conductance)


def assemble_graph_laplacian(
    node_p: Iterable[int],
    node_n: Iterable[int],
    conductance: Iterable[float],
    *,
    requested: str = "auto",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    positive = np.asarray(tuple(node_p), dtype=np.int64)
    negative = np.asarray(tuple(node_n), dtype=np.int64)
    values = np.asarray(tuple(conductance), dtype=np.float64)
    if positive.shape != negative.shape or positive.shape != values.shape:
        raise ValueError("Graph assembly inputs must have equal lengths.")
    if not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("Graph conductances must be finite and positive.")
    policy = choose_assembly_backend(len(values), requested)
    fallback = ""
    if policy["selected"] == "numba":
        try:
            rows, columns, triplet_values = _numba_laplacian_triplets(positive, negative, values)
        except Exception as exc:
            if policy["requested"] != "auto":
                raise AccelerationUnavailableError(str(exc)) from exc
            rows, columns, triplet_values = _numpy_laplacian_triplets(positive, negative, values)
            fallback = f"Numba JIT could not initialize; NumPy fallback used: {exc}"
            policy["selected"] = "numpy"
    else:
        rows, columns, triplet_values = _numpy_laplacian_triplets(positive, negative, values)
    return rows, columns, triplet_values, {
        **policy,
        "fallback": fallback,
        "fallback_used": bool(fallback),
    }
