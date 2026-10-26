# SPDX-License-Identifier: Apache-2.0
"""Current-driven passive land-port network; derivation in DC_ANNULAR_CIRCUIT.md."""
from __future__ import annotations
import math
import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


def solve_port_circuit(responses, edges, sources):
    """Responses use each body's last port as reference. No label-based wiring.

    edges: dictionaries {p:[body,port], n:[body,port], resistance_ohm:positive}.
    sources: one inward-current vector per body, with globally balanced sum.
    """
    require(type(responses) is list and 1 <= len(responses) <= 8 and len(sources) == len(responses),
            "Supply 1..8 explicit body responses and matching sources")
    require(type(edges) is list and 1 <= len(edges) <= 32, "Supply 1..32 positive-resistance edges")
    counts, matrices, injections = [], [], []
    for response, source in zip(responses, sources):
        z = np.asarray(response, dtype=float)
        require(z.ndim == 2 and z.shape[0] == z.shape[1] and z.shape[0] <= 7 and np.isfinite(z).all(),
                "Invalid reduced body response")
        if z.size:
            magnitude = float(np.max(np.abs(z)))
            require(0 < magnitude <= 1e12 and np.linalg.norm((z-z.T)/magnitude) <= 1e-9,
                    "Nonreciprocal or unsupported body response")
            eigenvalues = np.linalg.eigvalsh(z/magnitude)
            require(eigenvalues[0] > 0 and eigenvalues[-1]/eigenvalues[0] <= 1e12,
                    "Body response is not positive or exceeds condition budget")
        n = z.shape[0]+1
        s = np.asarray(source, dtype=float)
        require(s.shape == (n,) and np.isfinite(s).all() and np.max(np.abs(s)) <= 1e9,
                "Invalid inward body source currents")
        counts.append(n); matrices.append(z); injections.extend(s.tolist())
    offsets = np.r_[0, np.cumsum(counts)]
    size, nb, ne = int(offsets[-1]), len(counts), len(edges)
    zall, body = np.zeros((size, size)), np.zeros((size, nb))
    for b, z in enumerate(matrices):
        start = offsets[b]; n = counts[b]
        zall[start:start+n-1, start:start+n-1] = z
        body[start:start+n, b] = 1
    s = np.asarray(injections)
    scale_i = math.fsum(abs(v) for v in injections)
    require(abs(math.fsum(injections)) <= 64*np.finfo(float).eps*scale_i, "Unbalanced global current sources")
    incidence, resistance = np.zeros((size, ne)), []
    adjacency = [set() for _ in counts]
    for k, edge in enumerate(edges):
        require(type(edge) is dict and set(edge) == {"p", "n", "resistance_ohm"}, "Invalid edge fields")
        endpoints = []
        for label in ("p", "n"):
            endpoint = edge[label]
            require(type(endpoint) in (list, tuple) and len(endpoint) == 2
                    and all(type(v) is int for v in endpoint), "Invalid edge endpoint identity")
            b, port = endpoint
            require(0 <= b < nb and 0 <= port < counts[b], "Edge endpoint outside body ports")
            endpoints.append(int(offsets[b]+port))
        require(endpoints[0] != endpoints[1], "Edge endpoints must differ")
        value = edge["resistance_ohm"]
        require(type(value) in (int, float) and math.isfinite(value) and 1e-12 <= value <= 1e12,
                "Edge resistance must be finite positive within budget")
        resistance.append(value)
        incidence[endpoints[0], k] = 1; incidence[endpoints[1], k] = -1
        p, n = edge["p"][0], edge["n"][0]
        adjacency[p].add(n); adjacency[n].add(p)
    seen, pending = {0}, [0]
    while pending:
        for b in adjacency[pending.pop()]-seen:
            seen.add(b); pending.append(b)
    require(len(seen) == nb, "Disconnected body graph")
    resistance = np.asarray(resistance)
    scale_r = float(np.median(resistance))
    afree = incidence.T@body[:, 1:]
    h = np.diag(resistance)+incidence.T@zall@incidence
    matrix = np.block([[h/scale_r, -afree], [-afree.T, np.zeros((nb-1, nb-1))]])
    rhs = np.r_[incidence.T@zall@s/scale_r, -body[:, 1:].T@s]
    condition = float(np.linalg.cond(matrix))
    require(math.isfinite(condition) and condition <= 1e10, "Coupled circuit exceeds condition budget")
    solved = np.linalg.solve(matrix, rhs)
    norm_scale = max(float(np.max(np.abs(solved))), float(np.max(np.abs(rhs))))
    normalized_solution = solved/norm_scale if norm_scale else solved
    normalized_rhs = rhs/norm_scale if norm_scale else rhs
    residual = float(np.linalg.norm(matrix@normalized_solution-normalized_rhs))
    denominator = float(np.linalg.norm(matrix)*np.linalg.norm(normalized_solution)+np.linalg.norm(normalized_rhs))
    require(np.isfinite(solved).all() and residual <= 1e-10*denominator, "Circuit backward residual failed")
    j = solved[:ne]; gauge = np.r_[0., solved[ne:]*scale_r]
    current = s-incidence@j
    potential = zall@current+body@gauge
    kcl = body.T@current
    kvl = incidence.T@potential-resistance*j
    require(np.max(np.abs(kcl)) <= 1e-8*(scale_i+float(np.abs(j).sum())), "All-body KCL failed")
    scale_v = float(np.max(np.abs(potential)))+float(np.max(np.abs(resistance*j)))
    require(np.max(np.abs(kvl)) <= 1e-8*scale_v, "Circuit edge KVL failed")
    land_heat = [float(current[offsets[b]:offsets[b+1]]@zall[offsets[b]:offsets[b+1], offsets[b]:offsets[b+1]]
                       @current[offsets[b]:offsets[b+1]]) for b in range(nb)]
    edge_heat = resistance*j*j
    work = float(s@potential); total = math.fsum(land_heat)+float(edge_heat.sum())
    require(all(current[offsets[b]:offsets[b+1]].any() == (power > 0) for b, power in enumerate(land_heat))
            and np.all((j != 0) == (edge_heat > 0))
            and (scale_i == 0 or work > 0 and total > 0), "Circuit dissipation underflowed")
    require(np.isfinite(potential).all() and np.isfinite(edge_heat).all() and all(math.isfinite(v) and v >= 0 for v in land_heat)
            and math.isfinite(work) and abs(work-total) <= 1e-8*max(abs(work), total), "Circuit energy balance failed")
    return {"edge_current_a": j.tolist(), "edge_heat_w": edge_heat.tolist(), "body_gauge_v": gauge.tolist(),
        "body_currents_a": [current[offsets[b]:offsets[b+1]].tolist() for b in range(nb)],
        "body_port_potentials_v": [potential[offsets[b]:offsets[b+1]].tolist() for b in range(nb)],
        "body_heat_w": land_heat, "source_work_w": work, "total_heat_w": total,
        "diagnostics": {"condition": condition, "backward_residual": residual/denominator if denominator else 0.,
                        "maximum_body_kcl_a": float(np.max(np.abs(kcl))), "maximum_edge_kvl_v": float(np.max(np.abs(kvl)))}}
