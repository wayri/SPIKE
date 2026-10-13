// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard } from "./boardParser";
import type { SpiceWorkspace } from "./spiceWorkspace";
export type StudioPin = {
    id: string;
    pin: string;
    net_id: string;
    net_name: string;
    x_mm: number;
    y_mm: number;
};
export type StudioPart = {
    id: string;
    ref: string;
    value: string;
    cross_selection_id: string;
    placement: {
        x_mm: number;
        y_mm: number;
        rotation_deg: number;
        side: string;
    };
    pins: StudioPin[];
    model_binding: {
        status: "reviewed" | "unavailable";
        source_kind: string;
        model_id?: string;
        model_type?: string;
        model_pins?: string[];
        primitive?: string;
        value?: string;
        pin_bindings?: unknown[];
        parameters?: Record<string, unknown>;
        evidence?: string;
    };
};
export type StudioWire = {
    net_id: string;
    points_mm: [
        number,
        number
    ][];
    style: "wire" | "label";
    label: string;
};
export type StudioBoardCircuit = {
    contract: "spikes/studio-board-circuit-handoff/v1";
    source_design: {
        digest: string;
        occurrence_id: string;
        title: string; ground_node?:string;
    };
    components: StudioPart[];
    nets: {
        id: string;
        name: string;
        pins: {
            component_id: string;
            pin_id: string;
        }[];
    }[];
    wires: StudioWire[];
    diagnostics: string[];
};
const number = (value: number) => { if (!Number.isFinite(value))
    throw new Error("Circuit placement contains a nonfinite coordinate"); return value; };
export function studioBindingFingerprint(workspace: SpiceWorkspace, ref: string) { const assignment = workspace.assignments.find(row => row.component_ref === ref && row.enabled); return JSON.stringify([assignment, workspace.models.find(row => row.id === assignment?.model_id)]); }
/** Extract connectivity and original placements. Copper guides drawing, never circuit parameters. */
export function extractStudioBoardCircuit(board: ParsedBoard, workspace: SpiceWorkspace, digest: string, occurrenceId = "active-board", reviewed: Record<string, string> = {}): StudioBoardCircuit {
    if (!/^[a-f0-9]{64}$/i.test(digest) || !occurrenceId || occurrenceId.length > 256)
        throw new Error("A current design digest and board occurrence are required");
    if (board.components.length > 5000 || board.pads.length > 100000)
        throw new Error("Visual circuit extraction supports up to 5,000 parts and 100,000 pads");
    const diagnostics: string[] = [], netRows = new Map<string, {
        id: string;
        name: string;
        pins: {
            component_id: string;
            pin_id: string;
        }[];
    }>(), pinPoints = new Map<string, {
        part: string;
        pin: StudioPin;
    }[]>();
    const netIdsByName = new Map<string, string>();
    for (const [id, name] of Object.entries(board.nets)) {
        if (netIdsByName.has(name))
            throw new Error(`Ambiguous board net name ${name}; canonical identity is required`);
        netIdsByName.set(name, id);
    }
    const netId = (raw: string, name: string) => board.nets[raw] !== undefined ? raw : netIdsByName.get(name) ?? raw;
    const seenRefs = new Set<string>(), seenIds = new Set<string>();
    const padsByRef = new Map<string, typeof board.pads>();
    for (const pad of board.pads) {
        if (!pad.ref)
            continue;
        const rows = padsByRef.get(pad.ref) ?? [];
        rows.push(pad);
        padsByRef.set(pad.ref, rows);
    }
    const components = board.components.map(part => {
        if (seenRefs.has(part.ref) || seenIds.has(part.id))
            throw new Error("Duplicate board component identity must be resolved before extraction");
        seenRefs.add(part.ref);
        seenIds.add(part.id);
        const seenPins = new Set<string>(), pinNets = new Map<string, string>();
        const pins: StudioPin[] = [];
        for (const pad of padsByRef.get(part.ref) ?? []) {
            if (pad.type === "np_thru_hole" || !pad.net || !pad.name || board.nets[pad.net] === "")
                continue;
            const name = board.nets[pad.net] ?? pad.net;
            const id = netId(pad.net, name);
            if (pinNets.has(pad.name) && pinNets.get(pad.name) !== id)
                throw new Error(`Conflicting net assignments for ${part.ref} pin ${pad.name}`);
            pinNets.set(pad.name, id);
            const duplicate = `${pad.name}:${id}`;
            if (seenPins.has(duplicate))
                continue;
            seenPins.add(duplicate);
            const pin = { id: pad.id, pin: pad.name, net_id: id, net_name: name, x_mm: number(pad.at[0]), y_mm: number(pad.at[1]) };
            pins.push(pin);
            const net = netRows.get(id) ?? { id, name, pins: [] };
            net.pins.push({ component_id: part.id, pin_id: pad.id });
            netRows.set(id, net);
            const points = pinPoints.get(id) ?? [];
            points.push({ part: part.id, pin });
            pinPoints.set(id, points);
        }
        const assignment = workspace.assignments.find(row => row.enabled && row.component_ref === part.ref);
        const model = workspace.models.find(row => row.id === assignment?.model_id);
        const valid = assignment && model && model.pins.length === assignment.pin_bindings.length && new Set(assignment.pin_bindings.map(row => row.model_pin)).size === model.pins.length && assignment.pin_bindings.every(row => model.pins.includes(row.model_pin)) && assignment.pin_bindings.every(row => row.pad_id && row.circuit_node && (padsByRef.get(part.ref) ?? []).some(pad => pad.id === row.pad_id));
        const accepted = valid && reviewed[part.ref] === studioBindingFingerprint(workspace, part.ref);
        const binding: StudioPart["model_binding"] = accepted ? { status: "reviewed", source_kind: "spike-workspace", model_id: model!.id, model_type: model!.kind, model_pins: model!.pins, primitive: model!.primitive, value: model!.value, pin_bindings: assignment!.pin_bindings, parameters: model!.parameters, evidence: "User confirmed model and pad-to-model pin bindings" } : { status: "unavailable", source_kind: "spike-workspace", evidence: valid ? "Confirm model and pin mapping" : "Assign a model and complete its pin map" };
        return { id: part.id, ref: part.ref, value: part.value, cross_selection_id: `${digest}:${occurrenceId}:${part.ref}`, placement: { x_mm: number(part.at[0]), y_mm: number(part.at[1]), rotation_deg: number(part.rotation), side: part.layer.startsWith("B.") ? "bottom" : "top" }, pins, model_binding: binding };
    });
    const direction = new Map<string, {
        h: number;
        v: number;
        xs: number[];
        ys: number[];
    }>();
    for (const track of board.tracks) {
        if (!track.net)
            continue;
        const name = board.nets[track.net] ?? track.net;
        const id = netId(track.net, name);
        const row = direction.get(id) ?? { h: 0, v: 0, xs: [], ys: [] };
        row.h += Math.abs(track.end[0] - track.start[0]);
        row.v += Math.abs(track.end[1] - track.start[1]);
        if (row.xs.length < 256) {
            row.xs.push((track.start[0] + track.end[0]) / 2);
            row.ys.push((track.start[1] + track.end[1]) / 2);
        }
        direction.set(id, row);
    }
    const median = (values: number[], fallback: number) => values.length ? [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)] : fallback;
    const cellSize = Math.max(1, Math.max(board.width, board.height) / 32), spatial = new Map<string, StudioPart[]>();
    for (const part of components) {
        const key = `${Math.floor(part.placement.x_mm / cellSize)}:${Math.floor(part.placement.y_mm / cellSize)}`;
        const rows = spatial.get(key) ?? [];
        rows.push(part);
        spatial.set(key, rows);
    }
    const candidates = (start: [
        number,
        number
    ], end: [
        number,
        number
    ]) => { const rows: StudioPart[] = []; for (let x = Math.floor((Math.min(start[0], end[0]) - 1) / cellSize); x <= Math.floor((Math.max(start[0], end[0]) + 1) / cellSize); x++)
        for (let y = Math.floor((Math.min(start[1], end[1]) - 1) / cellSize); y <= Math.floor((Math.max(start[1], end[1]) + 1) / cellSize); y++)
            rows.push(...(spatial.get(`${x}:${y}`) ?? [])); return rows; };
    const wires: StudioWire[] = [];
    for (const net of netRows.values()) {
        const points = pinPoints.get(net.id) ?? [];
        if (points.length < 2) {
            diagnostics.push(`${net.name}: only one board pin; external excitation/connector remains explicit`);
        }
        if (points.length > 6) {
            for (const { pin } of points)
                wires.push({ net_id: net.id, points_mm: [[pin.x_mm, pin.y_mm]], style: "label", label: net.name });
            continue;
        }
        const d = direction.get(net.id);
        const horizontal = !d || d.h >= d.v;
        const ordered = [...points].sort((a, b) => horizontal ? a.pin.x_mm - b.pin.x_mm : a.pin.y_mm - b.pin.y_mm);
        const bus = horizontal ? median(d?.ys ?? [], ordered[0]?.pin.y_mm ?? 0) : median(d?.xs ?? [], ordered[0]?.pin.x_mm ?? 0);
        for (let i = 1; i < ordered.length; i++) {
            const a = ordered[i - 1], b = ordered[i];
            const route: [
                number,
                number
            ][] = horizontal ? [[a.pin.x_mm, a.pin.y_mm], [a.pin.x_mm, bus], [b.pin.x_mm, bus], [b.pin.x_mm, b.pin.y_mm]] : [[a.pin.x_mm, a.pin.y_mm], [bus, a.pin.y_mm], [bus, b.pin.y_mm], [b.pin.x_mm, b.pin.y_mm]];
            const obstructed = route.slice(1).some((end, index) => ((Math.abs(end[0] - route[index][0]) / cellSize + 3) * (Math.abs(end[1] - route[index][1]) / cellSize + 3) > 1024) || candidates(route[index], end).some(part => part.id !== a.part && part.id !== b.part && part.placement.x_mm > Math.min(route[index][0], end[0]) - 1 && part.placement.x_mm < Math.max(route[index][0], end[0]) + 1 && part.placement.y_mm > Math.min(route[index][1], end[1]) - 1 && part.placement.y_mm < Math.max(route[index][1], end[1]) + 1));
            if (obstructed) {
                for (const p of [a.pin, b.pin])
                    wires.push({ net_id: net.id, points_mm: [[p.x_mm, p.y_mm]], style: "label", label: net.name });
            }
            else
                wires.push({ net_id: net.id, points_mm: route, style: "wire", label: net.name });
        }
    }
    return { contract: "spikes/studio-board-circuit-handoff/v1", source_design: { digest, occurrence_id: occurrenceId, title: workspace.name, ground_node:workspace.ground_node }, components, nets: [...netRows.values()], wires, diagnostics };
}
export async function studioDesignDigest(design: Record<string, unknown>) {
    const stable = (value: unknown): unknown => Array.isArray(value) ? value.map(stable) : value && typeof value === "object" ? Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, row]) => [key, stable(row)])) : value;
    const bytes = new TextEncoder().encode(JSON.stringify(stable(design)));
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
}
