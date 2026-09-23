# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Experimental conservative DC probe; not a registered or qualified solver.

Independent RT0 mixed finite-element derivation (no external code consulted):
on a CCW triangle of area A, the outward unit-integrated-flux basis opposite
vertex v_i is w_i(x)=(x-v_i)/(2A). Its divergence integrates to one. With
sheet conductance k=sigma*t, M_ij=integral(w_i.w_j)/k is in ohms. Degree-two
three-point quadrature integrates this quadratic exactly. Assemble signed
shared-edge currents and piecewise-constant potentials: M q - B.T u = 0,
B q = s. This gives exact cell KCL and single-valued normal face flux. See
RT0 method lineage https://doi.org/10.1016/j.crma.2004.08.004; no elimination
algorithm or implementation from that article is used here.

All hanging rectangle-edge vertices are inserted before center-fan
triangulation. Pad terminals inject uniformly through their fixed finite
contact areas; the measured potential is the conjugate area-weighted cell
potential. Via currents use the same distribution and retain the physical
barrel resistance. Contact potentials are NOT collapsed to an equipotential.
This is a stated distributed-contact approximation, not a resolved 3D barrel
or solder joint. No AC, inductance, capacitance, or qualification is supplied.

Coordinates are mm, conductivity S/m, thickness mm, current A, voltage V.
An explicit unknown-count cap bounds the sparse problem size; sparse LU fill
and runtime are not tightly bounded, so this probe is for supervised offline
use. Diagonal resistance scaling improves saddle-system unit conditioning;
ill-shaped triangles and failed residual/energy checks fail closed.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any
import warnings

import numpy as np
from scipy.sparse import bmat, coo_matrix, diags
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import MatrixRankWarning, splu, spsolve

from .hybrid_mesh import HybridMesh


@dataclass
class RT0System:
    resistance: Any
    incidence: Any
    triangles_mm: np.ndarray
    triangle_nodes: np.ndarray
    areas_mm2: np.ndarray
    edges_mm: np.ndarray
    boundary_edges: np.ndarray
    contacts: dict[int, tuple[np.ndarray, np.ndarray]]
    planar_edge_count: int
    local_edges: np.ndarray
    local_resistance: np.ndarray


def triangle_resistance(vertices_mm: np.ndarray, sheet_conductance_s: float) -> np.ndarray:
    """Exact 3x3 RT0 mass in outward-face orientation (face i opposite v_i)."""
    vertices = np.asarray(vertices_mm, dtype=float)
    if vertices.shape != (3, 2) or not np.isfinite(vertices).all():
        raise ValueError("RT0 requires three finite planar vertices")
    if not np.isfinite(sheet_conductance_s) or sheet_conductance_s <= 0:
        raise ValueError("RT0 sheet conductance must be finite and positive")
    a, b = vertices[1] - vertices[0], vertices[2] - vertices[0]
    twice_area = float(a[0]*b[1] - a[1]*b[0])
    if twice_area <= 0 or max(float(a@a), float(b@b)) / twice_area > 1e5:
        raise ValueError("RT0 triangle is reversed, degenerate or ill-shaped")
    # Translation-free degree-two quadrature avoids subtracting large moments.
    relative = vertices - vertices[0]
    points = np.array([[2/3, 1/6, 1/6], [1/6, 2/3, 1/6], [1/6, 1/6, 2/3]]) @ relative
    basis = (points[:, None, :] - relative[None, :, :]) / twice_area
    return np.einsum("qik,qjk->ij", basis, basis) * twice_area / (6*sheet_conductance_s)


def _triangulate(mesh: HybridMesh, max_triangles: int):
    groups: dict[tuple[str, str], list[tuple[int, tuple[float, ...]]]] = {}
    for cell in mesh.cells:
        if cell.get("kind") != "surface":
            continue
        # The original mesh retains vertical barrel visualization quads;
        # electrical barrels enter separately through their finite R below.
        if cell.get("source_kind") == "via" and "control_node" not in cell:
            continue
        vertices = np.asarray(cell.get("vertices_mm"), dtype=float)
        if vertices.shape != (4, 3) or not np.isfinite(vertices).all():
            raise ValueError("RT0 requires finite axis-aligned rectangular surface cells")
        x0, y0 = vertices[0, :2]
        x1, y1 = vertices[2, :2]
        expected = np.array([[x0,y0], [x1,y0], [x1,y1], [x0,y1]])
        if (not np.array_equal(vertices[:, :2], expected) or x1-x0 < 1e-9
                or y1-y0 < 1e-9 or np.ptp(vertices[:, 2]) > 1e-12):
            raise ValueError("RT0 admits only positive axis-aligned constant-z rectangles")
        bounds = tuple(round(float(v), 12) for v in (x0,y0,x1,y1))
        groups.setdefault((cell["layer"], cell["net"]), []).append((int(cell["control_node"]), bounds))
    if not groups:
        raise ValueError("RT0 requires conforming surface cells")
    triangles, owners, keys = [], [], []
    from shapely.geometry import box
    from shapely.ops import unary_union
    for key, cells in groups.items():
        rectangles = [box(*bounds) for _, bounds in cells]
        area = sum(rectangle.area for rectangle in rectangles)
        if area - unary_union(rectangles).area > max(1e-12, 1e-11*area):
            raise ValueError("RT0 control rectangles overlap")
        vertical, horizontal = {}, {}
        for _, (x0,y0,x1,y1) in cells:
            for x in (x0,x1):
                vertical.setdefault(x, set()).update((y0,y1))
            for y in (y0,y1):
                horizontal.setdefault(y, set()).update((x0,x1))
        vertical = {x: sorted(ys) for x, ys in vertical.items()}
        horizontal = {y: sorted(xs) for y, xs in horizontal.items()}

        def between(values, low, high):
            return values[bisect_left(values, low):bisect_right(values, high)]

        for node, (x0,y0,x1,y1) in cells:
            boundary = ([(x,y0) for x in between(horizontal[y0],x0,x1)[:-1]]
                + [(x1,y) for y in between(vertical[x1],y0,y1)[:-1]]
                + [(x,y1) for x in between(horizontal[y1],x0,x1)[:0:-1]]
                + [(x0,y) for y in between(vertical[x0],y0,y1)[:0:-1]])
            center = ((x0+x1)/2, (y0+y1)/2)
            for a, b in zip(boundary, boundary[1:] + boundary[:1]):
                triangles.append((center,a,b))
                owners.append(node)
                keys.append(key)
                if len(triangles) > max_triangles:
                    raise ValueError("RT0 triangle work budget exceeded")
    return np.asarray(triangles), np.asarray(owners), keys


def assemble_conforming_dc(mesh: HybridMesh, *, max_unknowns: int = 150000,
                          hybridized: bool = False, max_triangles: int = 150000) -> RT0System:
    """Assemble all components; the port solve selects exactly one component."""
    if mesh.truncated or "conforming_partition" not in mesh.branch_admission:
        raise ValueError("RT0 rejects partial or nonconforming meshes")
    if not isinstance(max_unknowns, int) or not 10 <= max_unknowns <= 250000:
        raise ValueError("RT0 unknown budget must be an integer in 10..250000")
    if not isinstance(max_triangles, int) or not 4 <= max_triangles <= 250000:
        raise ValueError("RT0 local triangle budget must be an integer in 4..250000")
    triangles, owners, keys = _triangulate(mesh, max_triangles if hybridized else max_unknowns//2)
    materials = {}
    vias = []
    for branch in mesh.branches:
        if branch.kind == "via":
            vias.append(branch)
            continue
        if not branch.id.startswith("conforming:"):
            raise ValueError("RT0 rejects graph attachment and legacy planar branches")
        key = (branch.layer, branch.net)
        conductance = branch.conductivity_s_m*branch.thickness_mm*1e-3
        if key in materials and not np.isclose(materials[key], conductance, rtol=1e-12, atol=0):
            raise ValueError("RT0 requires uniform isotropic sheet conductance per layer/net")
        materials[key] = conductance
    edge_map, edges, counts = {}, [], []
    local_edges, local_signs, masses, areas = [], [], [], []
    for triangle, key in zip(triangles, keys):
        if key not in materials:
            raise ValueError("RT0 surface has no finite material-bearing planar face")
        masses.append(triangle_resistance(triangle, materials[key]))
        delta = triangle[1:] - triangle[0]
        areas.append((delta[0,0]*delta[1,1]-delta[0,1]*delta[1,0])/2)
        ids, signs = [], []
        for i in range(3):
            a, b = tuple(triangle[(i+1)%3]), tuple(triangle[(i+2)%3])
            signature = (key, tuple(sorted((a,b))))
            if signature not in edge_map:
                edge_map[signature] = len(edges)
                edges.append((a,b))
                counts.append(0)
            edge = edge_map[signature]
            counts[edge] += 1
            sign = 1 if edges[edge] == (a,b) else -1
            if counts[edge] > 2 or (counts[edge] == 2 and sign != -1):
                raise ValueError("RT0 mesh has nonmanifold or overlapping triangle edges")
            ids.append(edge)
            signs.append(sign)
        local_edges.append(ids)
        local_signs.append(signs)
    edge_count, triangle_count = len(edges), len(triangles)
    global_count = edge_count + (0 if hybridized else triangle_count) + len(vias)
    if global_count > max_unknowns:
        raise ValueError(f"RT0 {'hybrid' if hybridized else 'mixed'}-system unknown budget exceeded: "
            f"{global_count} > {max_unknowns}; triangles={triangle_count}, traces={edge_count}, vias={len(vias)}")
    local_edges, local_signs = np.asarray(local_edges), np.asarray(local_signs)
    local_masses = np.asarray(masses)
    masses = local_masses*local_signs[:,:,None]*local_signs[:,None,:]
    rows = np.repeat(local_edges, 3, axis=1).ravel().tolist()
    cols = np.tile(local_edges, (1,3)).ravel().tolist()
    values = masses.ravel().tolist()
    br = np.repeat(np.arange(triangle_count), 3).tolist()
    bc, bv = local_edges.ravel().tolist(), local_signs.ravel().tolist()
    areas = np.asarray(areas)
    contacts = {}
    contact_nodes = {int(contact["node"]) for contact in
        mesh.branch_admission["conforming_partition"].get("terminal_contacts", [])}
    for node in contact_nodes:
        indices = np.flatnonzero(owners == node)
        if not len(indices):
            raise ValueError("RT0 finite contact has no surface support")
        contacts[node] = (indices, areas[indices]/areas[indices].sum())
    for index, via in enumerate(vias, edge_count):
        resistance = via.resistance_ohm
        if not np.isfinite(resistance) or resistance <= 0:
            raise ValueError("RT0 requires positive finite barrel resistance")
        rows.append(index)
        cols.append(index)
        values.append(resistance)
        for node, sign in ((via.node_p,1), (via.node_n,-1)):
            if node not in contacts:
                raise ValueError("RT0 barrel endpoint lacks finite contact support")
            indices, weights = contacts[node]
            br.extend(indices.tolist())
            bc.extend([index]*len(indices))
            bv.extend((sign*weights).tolist())
    current_count = edge_count + len(vias)
    resistance = coo_matrix((values,(rows,cols)), shape=(current_count,current_count)).tocsr()
    incidence = coo_matrix((bv,(br,bc)), shape=(triangle_count,current_count)).tocsr()
    return RT0System(resistance, incidence, triangles, owners, areas, np.asarray(edges),
        np.flatnonzero(np.asarray(counts) == 1), contacts, edge_count, local_edges, local_masses)


def solve_conforming_dc(mesh: HybridMesh, source_node: int, load_node: int,
                        *, max_unknowns: int = 150000) -> dict[str, Any]:
    """One-ampere distributed-contact DC probe; disconnected ports fail closed."""
    if source_node == load_node:
        raise ValueError("RT0 source and load must be distinct finite contacts")
    system = assemble_conforming_dc(mesh, max_unknowns=max_unknowns)
    if source_node not in system.contacts or load_node not in system.contacts:
        raise ValueError("RT0 port terminals must resolve to fixed finite contacts")
    active_edges = np.setdiff1d(np.arange(system.incidence.shape[1]), system.boundary_edges)
    incidence = system.incidence[:, active_edges]
    # Bipartite graph avoids a dense clique among a via's distributed contacts.
    graph = bmat([[None, abs(incidence)], [abs(incidence.T), None]], format="csr")
    _, labels = connected_components(graph, directed=False)
    source_indices, source_weights = system.contacts[source_node]
    load_indices, load_weights = system.contacts[load_node]
    component = labels[source_indices[0]]
    if np.any(labels[np.r_[source_indices, load_indices]] != component):
        raise ValueError("RT0 port contacts are disconnected")
    cells = np.flatnonzero(labels[:incidence.shape[0]] == component)
    edge_selection = np.flatnonzero(labels[incidence.shape[0]:] == component)
    edge_ids = active_edges[edge_selection]
    b = system.incidence[cells][:,edge_ids]
    m = system.resistance[edge_ids][:,edge_ids]
    injection = np.zeros(system.incidence.shape[0])
    injection[source_indices] += source_weights
    injection[load_indices] -= load_weights
    rhs_cells = injection[cells]
    scale = float(np.median(m.diagonal()))
    # One cell potential is the gauge, not an ideal finite-length conductor.
    reduced = b[1:]
    matrix = bmat([[m/scale, -reduced.T], [-reduced, None]], format="csc")
    rhs = np.r_[np.zeros(len(edge_ids)), -rhs_cells[1:]]
    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        try:
            solution = spsolve(matrix, rhs)
        except (MatrixRankWarning, RuntimeError) as error:
            raise ValueError("RT0 sparse solve is singular or failed") from error
    if not np.isfinite(solution).all():
        raise ValueError("RT0 sparse solve returned nonfinite values")
    currents = solution[:len(edge_ids)]
    potentials = np.r_[0.0, solution[len(edge_ids):]]*scale
    kcl = float(np.max(np.abs(b@currents-rhs_cells)))
    residual = float(np.linalg.norm(matrix@solution-rhs)/max(np.linalg.norm(rhs), 1e-30))
    resistance = float(rhs_cells@potentials)
    loss = float(currents@(m@currents))
    energy_error = abs(loss-resistance)/max(abs(resistance), 1e-30)
    if residual > 1e-7 or kcl > 1e-8 or resistance <= 0 or energy_error > 1e-7:
        raise ValueError(f"RT0 solve failed conservation/energy checks: residual={residual:g}, KCL={kcl:g}")
    return {"model_status": "experimental", "production_qualified": False,
        "method": "conforming_triangle_RT0_mixed_DC",
        "contact_model": "uniform finite-area current injection; area-average potential",
        "resistance_ohm": resistance, "dissipation_w_at_one_ampere": loss,
        "maximum_cell_kcl_error_a": kcl, "relative_residual": residual,
        "relative_energy_error": energy_error,
        "triangle_count": len(cells), "current_unknown_count": len(edge_ids),
        "system_nonzeros": int(matrix.nnz),
        "geometry_snap_tolerance_mm": 5e-13,
        "limitations": ["DC only; no PEEC L/C or field qualification",
            "finite-area distributed contacts and uniform axial via current",
            "boundary copper omission and contact model need separate convergence",
            "sparse LU fill and runtime are not tightly bounded"]}


def solve_hybridized_conforming_dc(mesh: HybridMesh, source_node: int, load_node: int,
                                  *, max_unknowns: int = 150000,
                                  max_triangles: int = 150000) -> dict[str, Any]:
    """Equivalent RT0 probe with local flux/pressure static condensation.

    Write v=M^-1*1, d=1.T*v, a=1/d, b=v/d, H=M^-1-v*v.T/d.
    Local elimination gives q=b*s-H*lambda, u=a*s+b.T*lambda. With
    distributed barrel incidence C and barrel currents j, s=s0-C*j.
    Assembly gives [S G; G.T -D] [lambda;j]=[F*s0;-C.T*a*s0],
    where S=sum(H), F assembles b, G=F*C and D=Rvia+C.T*diag(a)*C.
    D is positive definite. The trace Schur S+G*D^-1*G.T is positive
    definite after one gauge in the driven connected component. Solve the
    sparse augmented form to avoid explicitly forming a dense inverse/Schur.
    Boundary traces are retained with zero external normal current. All
    local fluxes are recovered and checked, including the eliminated gauge.
    """
    if source_node == load_node:
        raise ValueError("RT0 source and load must be distinct finite contacts")
    system = assemble_conforming_dc(mesh, max_unknowns=max_unknowns,
        hybridized=True, max_triangles=max_triangles)
    if source_node not in system.contacts or load_node not in system.contacts:
        raise ValueError("RT0 port terminals must resolve to fixed finite contacts")
    nt = len(system.triangles_mm)
    ne = system.planar_edge_count
    nv = system.incidence.shape[1]-ne
    source_indices, source_weights = system.contacts[source_node]
    load_indices, load_weights = system.contacts[load_node]
    graph = bmat([[None, abs(system.incidence)], [abs(system.incidence.T), None]], format="csr")
    _, labels = connected_components(graph, directed=False)
    component = labels[source_indices[0]]
    if np.any(labels[np.r_[source_indices,load_indices]] != component):
        raise ValueError("RT0 port contacts are disconnected")
    cells = np.flatnonzero(labels[:nt] == component)
    traces = np.flatnonzero(labels[nt:nt+ne] == component)
    via_ids = np.flatnonzero(labels[nt+ne:] == component)
    injection = np.zeros(nt)
    injection[source_indices] += source_weights
    injection[load_indices] -= load_weights

    inverse = np.linalg.inv(system.local_resistance)
    v = inverse.sum(axis=2)
    a = 1/v.sum(axis=1)
    b = v*a[:,None]
    h_local = inverse - v[:,:,None]*v[:,None,:]*a[:,None,None]
    # Enforce the analytically zero row sums at floating-point precision.
    # This removes cancellation in the diagonal, not a PSD or model repair.
    for i in range(3):
        h_local[:,i,i] = -sum(h_local[:,i,j] for j in range(3) if j != i)
    edge_ids = system.local_edges
    rows = np.repeat(edge_ids, 3, axis=1).ravel()
    cols = np.tile(edge_ids, (1,3)).ravel()
    s = coo_matrix((h_local.ravel(), (rows,cols)), shape=(ne,ne)).tocsr()
    f_operator = coo_matrix((b.ravel(), (edge_ids.ravel(), np.repeat(np.arange(nt),3))),
        shape=(ne,nt)).tocsr()
    c = system.incidence[:,ne:]
    g = (f_operator@c).tocsr()
    via_r = system.resistance.diagonal()[ne:]
    d = (diags(via_r) + c.T@diags(a)@c).tocsr()
    f = np.asarray(f_operator@injection)
    h = np.asarray(c.T@(a*injection))
    # Keep the same terminal support and finite R; only a trace gauge is fixed.
    free = traces[1:]
    scale = float(np.median(system.resistance.diagonal()))
    g_selected = g[free][:,via_ids]
    matrix = bmat([[s[free][:,free]*scale, g_selected],
        [g_selected.T, -d[via_ids][:,via_ids]/scale]], format="csc")
    rhs = np.r_[f[free], -h[via_ids]/scale]
    try:
        factor = splu(matrix)
        solution = factor.solve(rhs)
    except RuntimeError as error:
        raise ValueError("Hybrid RT0 sparse solve is singular or failed") from error
    if not np.isfinite(solution).all():
        raise ValueError("Hybrid RT0 sparse solve returned nonfinite values")
    residual = float(np.linalg.norm(matrix@solution-rhs)/max(np.linalg.norm(rhs),1e-30))
    trace_potential = np.zeros(ne)
    trace_potential[free] = solution[:len(free)]*scale
    via_current = np.zeros(nv)
    via_current[via_ids] = solution[len(free):]
    local_source = injection-c@via_current
    local_trace = trace_potential[edge_ids]
    flux = b*local_source[:,None]-np.einsum("tij,tj->ti", h_local, local_trace)
    potential = a*local_source+np.einsum("ti,ti->t", b, local_trace)
    cell_kcl = float(np.max(np.abs(flux.sum(axis=1)+c@via_current-injection)))
    face_kcl = float(np.max(np.abs(np.bincount(edge_ids.ravel(), weights=flux.ravel(), minlength=ne))))
    resistance = float(injection@potential)
    loss = float(np.einsum("ti,tij,tj->",flux,system.local_resistance,flux)
        + np.dot(via_r,via_current**2))
    energy_error = abs(loss-resistance)/max(abs(resistance),1e-30)
    if (residual > 1e-7 or cell_kcl > 1e-8 or face_kcl > 1e-8
            or resistance <= 0 or energy_error > 1e-7):
        raise ValueError(f"Hybrid RT0 checks failed: residual={residual:g}, cell KCL={cell_kcl:g}, "
            f"face KCL={face_kcl:g}, energy={energy_error:g}")
    return {"model_status":"experimental", "production_qualified":False,
        "method":"conforming_triangle_RT0_hybridized_DC",
        "contact_model":"uniform finite-area current injection; area-average potential",
        "resistance_ohm":resistance, "dissipation_w_at_one_ampere":loss,
        "maximum_cell_kcl_error_a":cell_kcl, "maximum_face_kcl_error_a":face_kcl,
        "relative_residual":residual, "relative_energy_error":energy_error,
        "triangle_count":len(cells), "global_unknown_count":len(solution),
        "global_trace_count":len(traces), "via_current_unknown_count":len(via_ids),
        "system_nonzeros":int(matrix.nnz), "factor_nonzeros":int(factor.L.nnz+factor.U.nnz),
        "local_triangle_budget":max_triangles, "global_unknown_budget":max_unknowns,
        "geometry_snap_tolerance_mm":5e-13,
        "limitations":["DC only; no PEEC L/C or field qualification",
            "finite-area distributed contacts and uniform axial via current",
            "boundary copper omission and contact model need separate convergence",
            "sparse LU fill and runtime are not tightly bounded"]}
