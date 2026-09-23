"""Power-integrity error specifications for the canonical catalog.

The tuples are data-only so :mod:`spike_core.errors` remains responsible for
parsing, immutable metadata, redaction, and envelope behavior.
"""

from __future__ import annotations


PI_ERROR_SPECS = (
    (
        "SPIKE-BE-PI-E-0100",
        "PDN candidate invalid",
        "A decoupling candidate has invalid, unreviewed, or incompatible electrical placement data.",
        True,
        True,
        "Review the candidate values, endpoint mapping, frequency grid, and extraction provenance.",
    ),
    (
        "SPIKE-BE-PI-E-0001",
        "Terminal is not mapped to copper",
        "A source or load terminal could not be mapped to the selected connected conductor geometry.",
        True,
        True,
        "Select a pad, via, zone, or exact coordinate on the analyzed net and assign that object as the terminal anchor.",
    ),
    (
        "SPIKE-BE-PI-E-0002",
        "PI formulation is unsupported",
        "The selected PI solver does not support the requested analysis mode or formulation.",
        True,
        True,
        "Select a compatible DC, AC, transient, or circuit formulation and validate the setup again.",
    ),
    (
        "SPIKE-BE-PI-E-0003",
        "PI terminals are incomplete",
        "The PI request does not contain the source and load terminals required by the selected formulation.",
        True,
        True,
        "Assign at least one source and one load to exact copper objects, then validate the setup again.",
    ),
    (
        "SPIKE-BE-PI-E-0004",
        "Analyzed copper geometry is empty",
        "No usable connected copper geometry matched the managed nets in the PI request.",
        True,
        True,
        "Review the managed nets, import diagnostics, layer visibility, and mesh preview before retrying.",
    ),
    (
        "SPIKE-BE-PI-E-0005",
        "Load is disconnected from its source",
        "At least one load terminal is not electrically reachable from any configured source terminal.",
        True,
        True,
        "Correct terminal anchors or add the missing series-component and cross-net path definitions.",
    ),
    (
        "SPIKE-BE-PI-E-0006",
        "Source boundary conflict",
        "Two source definitions assign different voltages to the same connected conductor node.",
        True,
        True,
        "Remove the duplicate source or separate the conflicting source boundaries onto distinct conductor domains.",
    ),
    (
        "SPIKE-BE-PI-W-0001",
        "Floating copper excluded",
        "Copper outside the source-driven connected component was excluded from this result.",
        True,
        True,
        "Inspect the excluded geometry and add missing connectivity or terminals when it belongs to the intended current path.",
    ),
    (
        "SPIKE-BE-PI-W-0002",
        "Voltage-drop limit exceeded",
        "The solved voltage drop exceeds the configured design limit.",
        True,
        False,
        "Inspect the highlighted path, conductor geometry, contacts, and load definition before changing the limit.",
    ),
    (
        "SPIKE-BE-PI-W-0003",
        "Current-density limit exceeded",
        "The solved conductor current density exceeds the configured design limit.",
        True,
        False,
        "Inspect the identified conductor or via, then increase copper cross-section or reduce current where required.",
    ),
    (
        "SPIKE-BE-PI-W-0004",
        "Copper discretization requires convergence review",
        "The result uses a discretized copper representation that has not passed the configured mesh-convergence policy.",
        True,
        True,
        "Run the convergence study and review coarse-to-fine result agreement before engineering sign-off.",
    ),
    (
        "SPIKE-BE-PI-W-0005",
        "Ideal terminal package model used",
        "One or more source or load terminals use an ideal zero-resistance package or contact model.",
        True,
        True,
        "Assign measured or reviewed package and contact resistance models to the affected terminals.",
    ),
    (
        "SPIKE-BE-PI-W-0006",
        "Isolated secondary simplified",
        "An isolated secondary is represented as a local DC boundary without transformer magnetic behavior.",
        True,
        True,
        "Assign a coupled transformer or circuit model when leakage, saturation, loss, or regulation must be included.",
    ),
    (
        "SPIKE-BE-PI-I-0001",
        "Explicit return path solved",
        "The PI solve includes explicit supply and return conductors in the paired current loop.",
        True,
        False,
        "No action is required.",
    ),
    (
        "SPIKE-BE-PI-W-0101",
        "PDN multiport approximation",
        "PDN multiport extraction uses a shared ideal reference; return-path and differential PCB physics are not validated.",
        True,
        False,
        "Use the result for screening only; obtain an independently validated power/return extraction for return-path or differential analysis.",
    ),
    (
        "SPIKE-BE-PI-E-0102",
        "PDN candidate port extraction failed",
        "PDN candidate ports could not be extracted or mapped from terminals to the mesh.",
        True,
        True,
        "Review explicit source, observation, and candidate terminals, then correct their mesh mapping and retry.",
    ),
    (
        "SPIKE-BE-PI-P-0103",
        "PDN candidate port limit exceeded",
        "The requested PDN candidate ports exceed the configured extraction resource limit.",
        True,
        True,
        "Reduce the candidate count, run bounded batches, or raise the approved limit up to the hard maximum.",
    ),
)


__all__ = ["PI_ERROR_SPECS"]
