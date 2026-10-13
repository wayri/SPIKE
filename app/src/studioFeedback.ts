// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard } from "./boardParser";
import { studioBindingFingerprint } from "./studioBoardCircuit";
import type { SpiceNetlistPreview, SpiceWorkspace } from "./spiceWorkspace";
export type StudioThermalBinding = {
    reference: string;
    capacitance: string;
    thermalResistance: string;
    tcr: string;
    referenceTemperature: string;
    initialTemperature: string;
    minimumTemperature: string;
    maximumTemperature: string;
    confirmed: boolean;
    confirmation?: string;
    geometry?: {
        length: string;
        width: string;
        thickness: string;
        resistivity: string;
        expansion: string;
    };
};
export type StudioFeedbackSetup = {
    mode: "steady_state" | "transient";
    ambient: string;
    stopTime: string;
    window: string;
    electricalStep: string;
    bindings: StudioThermalBinding[];
    losslessConfirmed: boolean;
};
export type StudioFeedbackFrame = {
    time_s: number;
    temperature_k: Record<string, number>;
    node_power_w: Record<string, number>;
    electrical: {
        node_voltage_v: Record<string, number>;
        element_current_a: Record<string, number>;
        element_power_w: Record<string, number>;
        resistance_ohm: Record<string, number>;
    };
    geometry?: Record<string, Record<string, number>>;
    iteration: number;
    temperature_residual_k: number;
    power_residual_w: number;
    balance_residual_w: number;
};
export type StudioFeedbackResult = {
    status: string;
    model_status: string;
    frames: StudioFeedbackFrame[];
    limitations?: string[];
    [key: string]: unknown;
};
export const defaultStudioFeedback = (): StudioFeedbackSetup => ({ mode: "transient", ambient: "", stopTime: "0.1", window: "0.01", electricalStep: "0.001", bindings: [], losslessConfirmed: false });
const finite = (text: string, label: string, positive = false) => { if (!text.trim())
    throw new Error(`${label} is required`); const value = Number(text); if (!Number.isFinite(value) || (positive && value <= 0))
    throw new Error(`${label} must be finite${positive ? " and positive" : ""}`); return value; };
export function buildStudioFeedbackRequest(board: ParsedBoard, workspace: SpiceWorkspace, preview: SpiceNetlistPreview, revision: string, setup: StudioFeedbackSetup) {
    if (preview.status !== "ready" || !preview.netlist)
        throw new Error("Compose and validate the current circuit first");
    if (!/^[a-f0-9]{64}$/i.test(revision))
        throw new Error("A current board revision is required");
    if (!setup.losslessConfirmed)
        throw new Error("Confirm the uncoupled ideal-device loss assumptions");
    const ambient = finite(setup.ambient, "Ambient temperature (K)", true), aliases = preview.element_aliases;
    const assignments = workspace.assignments.filter(row => row.enabled && workspace.models.find(model => model.id === row.model_id)?.primitive === "resistor");
    if (!assignments.length)
        throw new Error("Assign at least one explicit resistor model to a board part");
    const nodes: Record<string, unknown>[] = [], links: Record<string, unknown>[] = [], bindings: Record<string, unknown>[] = [];
    for (const assignment of assignments) {
        const part = board.components.find(row => row.ref === assignment.component_ref), setupRow = setup.bindings.find(row => row.reference === assignment.component_ref);
        const element = aliases?.[assignment.component_ref];
        if (!part || !setupRow?.confirmed || setupRow.confirmation !== studioBindingFingerprint(workspace, assignment.component_ref) || !element)
            throw new Error(`Confirm model, pins and thermal data for ${assignment.component_ref}`);
        const id = `thermal_${part.id}`;
        nodes.push({ id, capacitance_j_per_k: finite(setupRow.capacitance, `${part.ref} heat capacity (J/K)`, true), initial_temperature_k: finite(setupRow.initialTemperature, `${part.ref} initial temperature (K)`, true), minimum_temperature_k: finite(setupRow.minimumTemperature, `${part.ref} model minimum temperature (K)`, true), maximum_temperature_k: finite(setupRow.maximumTemperature, `${part.ref} model maximum temperature (K)`, true) });
        links.push({ id: `ambient_${part.id}`, from_id: id, to_id: "ambient", resistance_k_per_w: finite(setupRow.thermalResistance, `${part.ref} thermal resistance (K/W)`, true) });
        const binding: Record<string, unknown> = { element_id: element, component_id: part.id, thermal_node_id: id, reference_temperature_k: finite(setupRow.referenceTemperature, `${part.ref} reference temperature (K)`, true), temperature_coefficient_per_k: finite(setupRow.tcr, `${part.ref} TCR (1/K)`) };
        if (setupRow.geometry) {
            const g = setupRow.geometry;
            binding.geometry = { length_m: finite(g.length, `${part.ref} conductor length (m)`, true), width_m: finite(g.width, `${part.ref} conductor width (m)`, true), thickness_m: finite(g.thickness, `${part.ref} conductor thickness (m)`, true), resistivity_ohm_m: finite(g.resistivity, `${part.ref} resistivity (ohm m)`, true), expansion_per_k: finite(g.expansion, `${part.ref} expansion (1/K)`) };
        }
        bindings.push(binding);
    }
    return { contract: "spike/studio-board-cosimulation-request/v1", netlist: preview.netlist, board_revision: revision, mode: setup.mode, bindings, thermal: { ambient_temperature_k: ambient, nodes, links }, controls: { window_s: finite(setup.window, "Coupling window (s)", true), electrical_step_s: finite(setup.electricalStep, "Electrical step (s)", true), stop_time_s: finite(setup.stopTime, "Stop time (s)", true), maximum_iterations: 30, temperature_tolerance_k: 1e-6, power_tolerance_w: 1e-8, balance_tolerance_w: 1e-7, relaxation: 1, time_limit_s: 120 } };
}
