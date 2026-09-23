"""Matrix assembly helpers for mixed physical and topology-only PEEC meshes."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from .hybrid_mesh import HybridMesh
from .peec_network import dense


class TopologyResistanceSolver:
    """Expand valid native resistance while retaining any degenerate link loss."""

    def __init__(self, solver: Any, mesh: HybridMesh, modeled_indices: Sequence[int]) -> None:
        self._solver = solver
        self._mesh = mesh
        self._modeled_indices = list(modeled_indices)

    def compute_resistance(self, frequency: float) -> np.ndarray:
        result = np.zeros((len(self._mesh.branches), len(self._mesh.branches)), dtype=float)
        if self._modeled_indices:
            modeled = dense(self._solver.compute_resistance(frequency))
            result[np.ix_(self._modeled_indices, self._modeled_indices)] = modeled
        modeled_set = set(self._modeled_indices)
        for index, branch in enumerate(self._mesh.branches):
            if index not in modeled_set:
                # Zero-length contacts cannot enter the native filament API.
                # Preserve their (normally zero) mesh resistance explicitly.
                result[index, index] = branch.resistance_ohm
        return result


def embed_physical_inductance(
    physical_inductance: np.ndarray,
    branch_count: int,
    physical_indices: Sequence[int],
) -> np.ndarray:
    """Embed physical L in a full matrix with zero-energy graph-link rows."""

    result = np.zeros((branch_count, branch_count), dtype=float)
    result[np.ix_(physical_indices, physical_indices)] = physical_inductance
    return result
