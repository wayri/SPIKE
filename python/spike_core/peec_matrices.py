"""Matrix assembly helpers for mixed physical and topology-only PEEC meshes."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from .hybrid_mesh import HybridMesh
from .peec_network import dense


def connected_component(mesh: HybridMesh, net: str, source_node: int) -> tuple[list[int], list[int]]:
    """Return nodes and branches reachable from a terminal on one net."""
    adjacency: dict[int, list[tuple[int, int]]] = {}
    for index, branch in enumerate(mesh.branches):
        if branch.net != net:
            continue
        adjacency.setdefault(branch.node_p, []).append((branch.node_n, index))
        adjacency.setdefault(branch.node_n, []).append((branch.node_p, index))
    nodes = {source_node}
    branches: set[int] = set()
    pending = [source_node]
    while pending:
        for neighbor, index in adjacency.get(pending.pop(), []):
            branches.add(index)
            if neighbor not in nodes:
                nodes.add(neighbor)
                pending.append(neighbor)
    return sorted(nodes), sorted(branches)


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
