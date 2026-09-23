import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, BarChart3, CheckCircle2, CircleHelp, FileInput, GitBranch, Link2,
  Copy, Download, FileText, LayoutGrid, Maximize2, Move, Network, Plus, RefreshCw, RotateCcw, Route, Save, Search,
  Settings2, Table2, Trash2, X, ZoomIn, ZoomOut, Undo2, Redo2,
} from "lucide-react";
import type { ParsedBoard } from "./boardParser";
import { previewViewportTarget } from "./BoardViewport";
import CircuitSymbol, { paletteSymbol } from "./CircuitSymbol";
import { schematicWire } from "./schematicGeometry";
import TopologyGenerator from "./TopologyGenerator";
import TopologyPreview from "./TopologyPreview";
import { appendTopology } from "./topologyGeneration";
import "./schematic.css";
import { isDesktopShell, runLocalWorker } from "./workerBridge";
import { numericMaximum, numericMinimum } from "./numericRange";
import {
  buildPowerTreeAnalysisPlan, calculatePowerTree, defaultTopologyPorts, emptyTopology,
  extractPowerPathFromBoard, extractTopologyFromBoard, extractTopologyFromXmlNetlist, layoutTopology, topologyScenarios,
  topologyPorts, topologyToText, validateTopologyPorts,
  PowerTreeAnalysisPlan, TopologyDomain, TopologyEdge, TopologyModel, TopologyNode, TopologyNodeKind, TopologyPinRole, TopologyPort,
} from "./powerTree";

const kinds: Record<TopologyDomain, { kind: TopologyNodeKind; label: string; help: string }[]> = {
  pi: [
    { kind: "source", label: "Source", help: "Independent supply or upstream rail input." },
    { kind: "regulator", label: "Regulator", help: "Conversion stage with input, output, efficiency, and device model." },
    { kind: "transformer", label: "Transformer", help: "Isolated conversion boundary between return domains." },
    { kind: "rail", label: "Power rail", help: "Copper-net segment linking series stages and loads." },
    { kind: "return", label: "Return / ground", help: "Explicit reference or isolated return domain." },
    { kind: "connector", label: "Connector", help: "Pin-mapped board, harness, or assembly interface." },
    { kind: "harness", label: "Harness", help: "Cable path with length, gauge, resistance, and inductance." },
    { kind: "load", label: "Load", help: "Constant-current, constant-power, resistive, pulse, or SPICE load." },
    { kind: "passive", label: "Passive", help: "Series or shunt resistor, capacitor, inductor, ferrite, or diode." },
  ],
  si: [
    { kind: "driver", label: "Driver", help: "Signal source, IBIS model, or behavioral transmitter." },
    { kind: "channel", label: "Channel", help: "Extracted routed interconnect or imported network." },
    { kind: "connector", label: "Connector", help: "Pin-mapped discontinuity or board interface." },
    { kind: "harness", label: "Cable", help: "Cable or harness segment with propagation model." },
    { kind: "termination", label: "Termination", help: "Series, parallel, Thevenin, or modelled termination." },
    { kind: "receiver", label: "Receiver", help: "Signal sink, IBIS model, or behavioral receiver." },
  ],
};

const nextNode = (model: TopologyModel, kind: TopologyNodeKind): TopologyNode => ({
  id: `user-${kind}-${crypto.randomUUID()}`,
  kind,
  label: kinds[model.domain].find(item => item.kind === kind)?.label ?? kind,
  ports: defaultTopologyPorts(kind, model.domain),
  x: 70 + (model.nodes.length % 4) * 210,
  y: 50 + Math.floor(model.nodes.length / 4) * 90,
  origin: "user",
});

const topologyNodeWidth = 210;
const topologyNodeHeight = (node: TopologyNode, domain: TopologyDomain) => {
  const ports = topologyPorts(node, domain);
  return Math.max(112, 48 + Math.max(ports.filter(port => port.side === "left").length, ports.filter(port => port.side === "right").length) * 24);
};
const topologyPortPoint = (node: TopologyNode, domain: TopologyDomain, portId: string | undefined, fallbackSide: TopologyPort["side"] = "left") => {
  const ports = topologyPorts(node, domain);
  const port = ports.find(item => item.id === portId) ?? ports.find(item => item.side === fallbackSide) ?? ports[0];
  const side = port?.side ?? fallbackSide;
  const sidePorts = ports.filter(item => item.side === side);
  const index = Math.max(0, sidePorts.findIndex(item => item.id === port?.id));
  const height = topologyNodeHeight(node, domain);
  return { x: node.x + (side === "right" ? topologyNodeWidth : 0), y: node.y + ((index + 1) * height) / (sidePorts.length + 1) };
};

const optionalNumber = (value: string): number | undefined => value.trim() === "" ? undefined : Number(value);
const metric = (value: number, unit: string, digits = 2) => Number.isFinite(value) ? `${value.toFixed(digits)} ${unit}` : `-- ${unit}`;
const groundNet = /(^|[/_.+-])(gnd|agnd|dgnd|pgnd|vss)(?:$|[/_.+-])/i;
const circuitNodeName = (value: string) => `N_${value.replace(/[^a-z0-9_.:+-]+/gi, "_").replace(/^[^a-z_]+/i, "") || "NODE"}`.slice(0, 128);
const modelParameterFields: Record<string, { key: string; label: string; placeholder: string }[]> = {
  resistor: [{ key: "resistance_ohm", label: "Resistance (ohm)", placeholder: "0.01" }],
  inductor: [{ key: "inductance_h", label: "Inductance (H)", placeholder: "1e-6" }, { key: "series_resistance_ohm", label: "DCR (ohm)", placeholder: "0.02" }],
  capacitor: [{ key: "capacitance_f", label: "Capacitance (F)", placeholder: "10e-6" }, { key: "esr_ohm", label: "ESR (ohm)", placeholder: "0.01" }, { key: "esl_h", label: "ESL (H)", placeholder: "1e-9" }],
  diode: [{ key: "forward_voltage_v", label: "Forward voltage (V)", placeholder: "0.7" }, { key: "series_resistance_ohm", label: "Series R (ohm)", placeholder: "0.01" }],
  mosfet: [{ key: "rds_on_ohm", label: "RDS(on) (ohm)", placeholder: "0.005" }, { key: "threshold_v", label: "Threshold (V)", placeholder: "2.5" }, { key: "gate_charge_c", label: "Gate charge (C)", placeholder: "30e-9" }],
  spice_subcircuit: [{ key: "temperature_c", label: "Model temperature (C)", placeholder: "25" }],
  behavioral_block: [{ key: "behavior", label: "Behavior / expression", placeholder: "V(out)=f(Vin,I,T)" }],
};
const previewNode = (node: TopologyNode | undefined) => {
  if (!node) return previewViewportTarget(null);
  if (node.ref) return previewViewportTarget({ kind: "object", type: "component", ref: node.ref, net: node.net, label: node.label });
  if (node.net) return previewViewportTarget({ kind: "net", net: node.net, label: node.label });
  return previewViewportTarget(null);
};
const designForTopology = (board: ParsedBoard) => ({
  contract: "spike/v1",
  name: "topology-editor",
  source_format: "kicad",
  layers: board.layerDefinitions.map(layer => ({ id: layer.id, name: layer.name, type: layer.kind, user_name: layer.userName ?? "" })),
  nets: Object.entries(board.nets).map(([id, name]) => ({ id, name })),
  tracks: board.tracks.map(track => ({ ...track, net_name: track.net })),
  vias: board.vias.map(via => ({ ...via, net_name: via.net })),
  pads: board.pads.map(pad => ({ ...pad, component: pad.ref, net_name: pad.net })),
  zones: board.zones.map(zone => ({ ...zone, net_name: zone.net })),
  components: board.components.map(component => ({ ...component, reference: component.ref })),
  stackup: board.stackup,
  technology: board.technology ?? "rigid",
  regions: board.regions ?? [],
  bends: board.bendLines ?? [],
});

export default function TopologyEditor({
  domain, board, model, setModel, onClose, onUseForAnalysis, onStatus, onUndo, onRedo,
}: {
  domain: TopologyDomain;
  board: ParsedBoard | null;
  model: TopologyModel;
  setModel: (model: TopologyModel, record?: boolean) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  onClose: () => void;
  onUseForAnalysis: (model: TopologyModel, scenarioId: string, plan: PowerTreeAnalysisPlan) => void;
  onStatus: (message: string) => void;
}) {
  const treeName = domain === "pi" ? "Power Tree" : "Channel Tree";
  const scenarios = topologyScenarios(model);
  const [selectedId, setSelectedId] = useState(model.nodes[0]?.id ?? "");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set(model.nodes[0]?.id ? [model.nodes[0].id] : []));
  const [linkFrom, setLinkFrom] = useState<{ nodeId: string; portId: string } | null>(null);
  const [query, setQuery] = useState("");
  const [showReturns, setShowReturns] = useState(false);
  const [scenarioId, setScenarioId] = useState(scenarios[0]?.id ?? "typical");
  const [view, setView] = useState<"diagram" | "text" | "consumption" | "rails">("diagram");
  const [camera, setCamera] = useState({ x: 30, y: 28, zoom: 1 });
  const [pathWizardOpen, setPathWizardOpen] = useState(false);
  const [generatorOpen, setGeneratorOpen] = useState(false);
  const [extractionPreview, setExtractionPreview] = useState<TopologyModel | null>(null);
  const [fitPending, setFitPending] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(() => window.innerWidth >= 1100);
  const [pathMode, setPathMode] = useState<"add" | "replace">("add");
  const [modelAssistantOpen, setModelAssistantOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [pathSourcePadId, setPathSourcePadId] = useState("");
  const [pathLoadPadId, setPathLoadPadId] = useState("");
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId?: string } | null>(null);
  const [marquee, setMarquee] = useState<{ x: number; y: number; width: number; height: number } | null>(null);
  const [wirePointer, setWirePointer] = useState<{ x: number; y: number } | null>(null);
  const [pendingDestructive, setPendingDestructive] = useState<"clear" | "reset" | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const initialModelRef = useRef<TopologyModel>(structuredClone(model));
  const dragRef = useRef<{ pointerId: number; nodeId: string; clientX: number; clientY: number; recorded?: boolean; starts: Map<string, { x: number; y: number }> } | null>(null);
  const panRef = useRef<{ pointerId: number; clientX: number; clientY: number; x: number; y: number } | null>(null);
  const marqueeRef = useRef<{ pointerId: number; startX: number; startY: number; currentX: number; currentY: number } | null>(null);
  const canvasPoint = (clientX: number, clientY: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    return rect ? { x: clientX - rect.left, y: clientY - rect.top } : { x: 0, y: 0 };
  };
  const worldPoint = (clientX: number, clientY: number) => {
    const point = canvasPoint(clientX, clientY);
    return { x: (point.x - camera.x) / camera.zoom, y: (point.y - camera.y) / camera.zoom };
  };
  const scenario = scenarios.find(item => item.id === scenarioId) ?? scenarios[0];
  const budget = useMemo(() => calculatePowerTree(model, scenario?.id ?? "typical"), [model, scenario?.id]);
  const plan = useMemo(() => buildPowerTreeAnalysisPlan(model, scenario?.id ?? "typical"), [model, scenario?.id]);
  const textEquivalent = useMemo(() => topologyToText(model), [model]);
  const selected = model.nodes.find(node => node.id === selectedId);
  const searchText = query.toLowerCase();
  const visibleNodes = useMemo(() => model.nodes.filter(node =>
    (showReturns || node.kind !== "return") && `${node.label} ${node.ref ?? ""} ${node.net ?? ""} ${node.value ?? ""}`.toLowerCase().includes(searchText)),
  [model.nodes, searchText, showReturns]);
  const visibleIds = new Set(visibleNodes.map(node => node.id));
  const visibleEdges = model.edges.filter(edge => visibleIds.has(edge.from) && visibleIds.has(edge.to) && (showReturns || edge.kind !== "return"));
  const width = Math.max(900, numericMaximum(visibleNodes.map(node => node.x + topologyNodeWidth + 32), 900));
  const height = Math.max(480, numericMaximum(visibleNodes.map(node => node.y + topologyNodeHeight(node, domain) + 24), 480));
  const loads = visibleNodes.filter(node => node.kind === "load");
  const rails = budget.rails.filter(rail => {
    const node = model.nodes.find(item => item.id === rail.nodeId);
    return `${rail.net} ${node?.label ?? ""}`.toLowerCase().includes(searchText);
  });
  const powerPads = useMemo(() => (board?.pads ?? [])
    .filter(pad => pad.net && !groundNet.test(pad.net))
    .sort((left, right) => `${left.net} ${left.ref} ${left.name}`.localeCompare(`${right.net} ${right.ref} ${right.name}`, undefined, { numeric: true })), [board]);
  const selectedPads = selected?.ref ? (board?.pads ?? []).filter(pad => pad.ref === selected.ref) : [];
  const pathGroups = useMemo(() => {
    const groups = new Map<string, { id: string; label: string; nodes: number; nets: Set<string>; series: number }>();
    model.nodes.forEach(node => {
      if (!node.pathGroupId) return;
      const group = groups.get(node.pathGroupId) ?? { id: node.pathGroupId, label: node.pathGroupLabel ?? node.pathGroupId, nodes: 0, nets: new Set<string>(), series: 0 };
      group.nodes += 1;
      if (node.net) group.nets.add(node.net);
      if (node.orientation === "series" && node.kind !== "rail") group.series += 1;
      groups.set(node.pathGroupId, group);
    });
    return [...groups.values()];
  }, [model.nodes]);
  const activeModelFields = selected ? modelParameterFields[selected.simulationModel ?? ""] ?? [] : [];
  const modelReady = selected && (["resistor", "inductor", "capacitor", "dc_source", "constant_current", "constant_power", "resistive_load"].includes(selected.simulationModel ?? "")
    || (["spice_subcircuit", "mosfet", "diode", "behavioral_block", "isolated_transformer"].includes(selected.simulationModel ?? "") && Boolean(selected.modelLink)));

  const selectOnly = (id: string) => { setSelectedId(id); setSelectedIds(new Set(id ? [id] : [])); };
  const selectNodes = (ids: Iterable<string>, primary?: string) => {
    const next = new Set(ids);
    setSelectedIds(next);
    setSelectedId(primary && next.has(primary) ? primary : [...next][0] ?? "");
  };

  const patchSelected = (patch: Partial<TopologyNode>) => {
    setModel({ ...model, nodes: model.nodes.map(node => node.id === selectedId ? { ...node, ...patch } : node) });
  };
  const patchSelectedPort = (portId: string, patch: Partial<TopologyPort>) => {
    if (!selected) return;
    patchSelected({ ports: topologyPorts(selected, domain).map(port => port.id === portId ? { ...port, ...patch, bindingState: "bound" } : port) });
  };
  const addSelectedPort = () => {
    if (!selected) return;
    const ports = topologyPorts(selected, domain);
    const id = `port_${ports.length + 1}_${crypto.randomUUID().slice(0, 6)}`;
    patchSelected({ ports: [...ports, { id, label: `P${ports.length + 1}`, direction: "bidirectional", kind: domain === "si" ? "signal" : "power", side: ports.filter(port => port.side === "left").length <= ports.filter(port => port.side === "right").length ? "left" : "right", bindingState: "unassigned" }] });
  };
  const removeSelectedPort = (portId: string) => {
    if (!selected) return;
    setModel({
      ...model,
      nodes: model.nodes.map(node => node.id === selected.id ? { ...node, ports: topologyPorts(node, domain).filter(port => port.id !== portId) } : node),
      edges: model.edges.filter(edge => !(edge.from === selected.id && edge.fromPort === portId) && !(edge.to === selected.id && edge.toPort === portId)),
    });
    onStatus(`Removed port and its explicit connections from ${selected.label}`);
  };
  const replaceSelectedPorts = (mode: "generic" | "differential") => {
    if (!selected) return;
    const base = defaultTopologyPorts(selected.kind, domain, selected.orientation);
    const ports = mode === "differential" && domain === "si" ? base.flatMap(port => port.kind === "signal" ? [
      { ...port, id: `${port.id}_p`, label: `${port.label}+`, pair: port.id, bindingState: "unassigned" as const },
      { ...port, id: `${port.id}_n`, label: `${port.label}-`, pair: port.id, bindingState: "unassigned" as const },
    ] : [{ ...port, bindingState: "unassigned" as const }]) : base.map(port => ({ ...port, bindingState: "unassigned" as const }));
    setModel({ ...model, nodes: model.nodes.map(node => node.id === selected.id ? { ...node, ports } : node), edges: model.edges.filter(edge => edge.from !== selected.id && edge.to !== selected.id) });
    onStatus(`${selected.label} now uses the ${mode} port template; prior incident connections were removed for review`);
  };
  const fitDiagram = () => {
    const viewport = canvasRef.current;
    if (!viewport || !visibleNodes.length) { setCamera({ x: 30, y: 28, zoom: 1 }); return; }
    const minX = numericMinimum(visibleNodes.map(node => node.x));
    const minY = numericMinimum(visibleNodes.map(node => node.y));
    const maxX = numericMaximum(visibleNodes.map(node => node.x + topologyNodeWidth));
    const maxY = numericMaximum(visibleNodes.map(node => node.y + topologyNodeHeight(node, domain)));
    const zoom = Math.max(0.2, Math.min(1.4, Math.min((viewport.clientWidth - 90) / Math.max(1, maxX - minX), (viewport.clientHeight - 90) / Math.max(1, maxY - minY))));
    setCamera({ x: (viewport.clientWidth - (maxX - minX) * zoom) / 2 - minX * zoom, y: (viewport.clientHeight - (maxY - minY) * zoom) / 2 - minY * zoom, zoom });
  };
  const zoomAtCenter = (factor: number) => {
    const viewport = canvasRef.current;
    if (!viewport) return;
    const centerX = viewport.clientWidth / 2; const centerY = viewport.clientHeight / 2;
    setCamera(current => {
      const zoom = Math.max(0.2, Math.min(2.5, current.zoom * factor));
      const worldX = (centerX - current.x) / current.zoom; const worldY = (centerY - current.y) / current.zoom;
      return { x: centerX - worldX * zoom, y: centerY - worldY * zoom, zoom };
    });
  };
  const buildSelectedPath = async () => {
    if (!board || !pathSourcePadId || !pathLoadPadId) { onStatus("Select an input pad and output pad before tracing the path"); return; }
    try {
      if (isDesktopShell()) {
        const response = await runLocalWorker({
          method: "extract_power_path",
          params: { design: designForTopology(board), source: pathSourcePadId, sink: pathLoadPadId },
        });
        if (!response.ok) throw new Error(response.error ?? "The worker could not extract the selected power path.");
        if (response.result?.status === "no_path") {
          const warnings = Array.isArray(response.result.warnings) ? response.result.warnings.map(String) : [];
          throw new Error(warnings[warnings.length - 1] ?? "No non-ground component path connects the selected pads.");
        }
      }
      const extracted = extractPowerPathFromBoard(board, pathSourcePadId, pathLoadPadId);
      let next = extracted;
      if (pathMode === "add" && model.nodes.length) {
        const prefix = `path-${crypto.randomUUID().slice(0, 8)}-`;
        const idMap = new Map(extracted.nodes.map(node => [node.id, `${prefix}${node.id}`]));
        const yOffset = numericMaximum(model.nodes.map(node => node.y + 95), 95);
        const addedNodes = extracted.nodes.map(node => ({ ...node, id: idMap.get(node.id)!, pathGroupId: node.pathGroupId ? `${prefix}${node.pathGroupId}` : undefined, y: node.y + yOffset }));
        const addedEdges = extracted.edges.map(edge => ({ ...edge, id: `${prefix}${edge.id}`, from: idMap.get(edge.from)!, to: idMap.get(edge.to)! }));
        next = {
          ...model,
          nodes: [...model.nodes, ...addedNodes],
          edges: [...model.edges, ...addedEdges],
          extraction: {
            source: "board_netlist",
            generatedAt: new Date().toISOString(),
            warnings: [...new Set([...model.extraction.warnings, ...extracted.extraction.warnings])],
          },
        };
      }
      setModel(next); selectOnly(next.nodes[pathMode === "add" && model.nodes.length ? model.nodes.length : 0]?.id ?? ""); setScenarioId(topologyScenarios(next)[0].id);
      setPathWizardOpen(false); setCamera({ x: 30, y: 28, zoom: 1 });
      onStatus(`${pathMode === "add" ? "Added" : "Built"} source-to-load path with ${extracted.nodes.length} elements and ${extracted.edges.length} explicit connections`);
    } catch (error) { onStatus(error instanceof Error ? error.message : "Power-path extraction failed"); }
  };
  const removePathGroup = (pathGroupId: string) => {
    const removed = new Set(model.nodes.filter(node => node.pathGroupId === pathGroupId).map(node => node.id));
    const next = { ...model, nodes: model.nodes.filter(node => !removed.has(node.id)), edges: model.edges.filter(edge => !removed.has(edge.from) && !removed.has(edge.to)) };
    setModel(next);
    if ([...removed].some(id => selectedIds.has(id))) selectOnly(next.nodes[0]?.id ?? "");
    onStatus(`Removed one linked power path from the sheet`);
  };
  const patchPinRole = (pin: string, role: TopologyPinRole) => {
    if (!selected) return;
    const pinRoles = { ...selected.pinRoles, [pin]: role };
    const pins = selectedPads.filter(pad => !["unused", "control"].includes(pinRoles[pad.name] ?? "unused")).map(pad => ({ pad_id: pad.id, circuit_node: circuitNodeName(pad.net ?? pad.id), role: pinRoles[pad.name] }));
    patchSelected({ pinRoles, circuitModel: { ...selected.circuitModel, pins } });
  };
  const patchModelParameter = (key: string, value: string) => patchSelected({ modelParameters: { ...selected?.modelParameters, [key]: value } });
  const patchNode = (id: string, patch: Partial<TopologyNode>) => {
    setModel({ ...model, nodes: model.nodes.map(node => node.id === id ? { ...node, ...patch } : node) });
  };
  const copyTopology = async (format: "text" | "json") => {
    const content = format === "text" ? textEquivalent : `${JSON.stringify(model, null, 2)}\n`;
    try {
      await navigator.clipboard.writeText(content);
      onStatus(`${domain === "pi" ? "Power Tree" : "Channel Tree"} ${format === "text" ? "text description" : "canonical JSON"} copied`);
    } catch {
      onStatus("Clipboard access was denied; use Export text instead");
    }
  };
  const exportTopologyText = () => {
    const url = URL.createObjectURL(new Blob([textEquivalent], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${model.name.replace(/[^a-z0-9._-]+/gi, "-").replace(/^-|-$/g, "") || model.domain}-topology.spike-topology.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
    onStatus(`${domain === "pi" ? "Power Tree" : "Channel Tree"} text description exported`);
  };
  const patchOperatingPoint = (node: TopologyNode, patch: { enabled?: boolean; currentA?: number; powerW?: number }) => {
    patchNode(node.id, { operatingPoints: { ...node.operatingPoints, [scenario.id]: { ...node.operatingPoints?.[scenario.id], ...patch } } });
  };
  const patchScenario = (loadMultiplier: number) => {
    const next = scenarios.map(item => item.id === scenario.id ? { ...item, loadMultiplier: Math.max(0, loadMultiplier) } : item);
    setModel({ ...model, scenarios: next });
  };
  const addScenario = () => {
    const id = `case-${crypto.randomUUID().slice(0, 8)}`;
    setModel({ ...model, scenarios: [...scenarios, { id, label: `Case ${scenarios.length + 1}`, loadMultiplier: 1 }] });
    setScenarioId(id);
  };
  const addNode = (kind: TopologyNodeKind) => {
    const node = nextNode(model, kind);
    setModel({ ...model, nodes: [...model.nodes, node], extraction: { ...model.extraction, warnings: model.extraction.warnings.filter(warning => !warning.startsWith("No topology")) } });
    selectOnly(node.id);
  };
  const deleteSelected = () => {
    const removed = selectedIds.size ? selectedIds : new Set(selected ? [selected.id] : []);
    if (!removed.size) return;
    setModel({ ...model, nodes: model.nodes.filter(node => !removed.has(node.id)), edges: model.edges.filter(edge => !removed.has(edge.from) && !removed.has(edge.to)) });
    selectNodes([]);
    onStatus(`Deleted ${removed.size} selected ${treeName} element${removed.size === 1 ? "" : "s"}`);
  };
  const duplicateSelected = () => {
    if (!selectedIds.size) return;
    const idMap = new Map<string, string>();
    const nodes = model.nodes.filter(node => selectedIds.has(node.id)).map(node => {
      const id = `copy-${crypto.randomUUID()}`; idMap.set(node.id, id);
      return { ...structuredClone(node), id, label: `${node.label} copy`, x: node.x + 30, y: node.y + 30, origin: "user" as const };
    });
    const edges = model.edges.filter(edge => idMap.has(edge.from) && idMap.has(edge.to)).map(edge => ({ ...structuredClone(edge), id: `copy-edge-${crypto.randomUUID()}`, from: idMap.get(edge.from)!, to: idMap.get(edge.to)!, origin: "user" as const }));
    setModel({ ...model, nodes: [...model.nodes, ...nodes], edges: [...model.edges, ...edges] });
    selectNodes(nodes.map(node => node.id));
    onStatus(`Duplicated ${nodes.length} ${treeName} element${nodes.length === 1 ? "" : "s"}`);
  };
  const arrangeDiagram = () => {
    setModel({ ...model, nodes: layoutTopology(model.nodes, model.edges) });
    setFitPending(true);
    setPendingDestructive(null);
    onStatus(`${treeName} elements arranged from ${domain === "pi" ? "sources to loads" : "transmitters to receivers"}`);
  };
  const runDestructive = (action: "clear" | "reset") => {
    if (pendingDestructive !== action) {
      setPendingDestructive(action);
      onStatus(`Select ${action === "clear" ? "Confirm clear" : "Confirm reset"} to continue; this changes the current ${treeName} sheet`);
      return;
    }
    if (action === "clear") {
      const next = emptyTopology(domain);
      setModel({ ...next, name: model.name, scenarios: structuredClone(model.scenarios) });
      selectNodes([]);
      onStatus(`${treeName} canvas cleared`);
    } else {
      const next = structuredClone(initialModelRef.current);
      setModel(next);
      selectOnly(next.nodes[0]?.id ?? "");
      setScenarioId(topologyScenarios(next)[0]?.id ?? "typical");
      setCamera({ x: 30, y: 28, zoom: 1 });
      onStatus(`${treeName} canvas reset to the state opened in this workbench`);
    }
    setLinkFrom(null); setContextMenu(null); setPendingDestructive(null);
  };
  const connectNodes = (from: string, target: string, requestedFromPort?: string, requestedToPort?: string) => {
    if (!from || !target || from === target) return;
    const fromNode = model.nodes.find(node => node.id === from);
    const toNode = model.nodes.find(node => node.id === target);
    if (!fromNode || !toNode) return;
    const fromPorts = topologyPorts(fromNode, domain);
    const toPorts = topologyPorts(toNode, domain);
    const fromPort = fromPorts.find(port => port.id === requestedFromPort)
      ?? fromPorts.find(port => port.side === "right" && ["output", "bidirectional", "passive"].includes(port.direction));
    const toPort = toPorts.find(port => port.id === requestedToPort)
      ?? toPorts.find(port => port.side === "left" && ["input", "bidirectional", "passive", "reference"].includes(port.direction));
    if (!fromPort || !toPort) { onStatus("Select compatible source and destination ports before connecting these blocks"); return; }
    if (["input", "control"].includes(fromPort.direction) || toPort.direction === "output") {
      onStatus(`Port directions are incompatible: ${fromNode.label}.${fromPort.label} (${fromPort.direction}) to ${toNode.label}.${toPort.label} (${toPort.direction})`); return;
    }
    const electricalClass = (port: TopologyPort) => ["return", "reference", "shield"].includes(port.kind) ? "reference" : port.kind;
    if (electricalClass(fromPort) !== electricalClass(toPort)) {
      onStatus(`Port kinds are incompatible: ${fromNode.label}.${fromPort.label} (${fromPort.kind}) to ${toNode.label}.${toPort.label} (${toPort.kind})`); return;
    }
    if (model.edges.some(edge => edge.from === from && edge.to === target && edge.fromPort === fromPort.id && edge.toPort === toPort.id)) {
      onStatus(`Ports ${fromPort.label} and ${toPort.label} are already connected`); return;
    }
    const countConnections = (nodeId: string, portId: string) => model.edges.filter(edge =>
      (edge.from === nodeId && edge.fromPort === portId) || (edge.to === nodeId && edge.toPort === portId)).length;
    if (fromPort.maximumConnections !== undefined && countConnections(from, fromPort.id) >= fromPort.maximumConnections) {
      onStatus(`${fromNode.label}.${fromPort.label} has reached its connection limit`); return;
    }
    if (toPort.maximumConnections !== undefined && countConnections(target, toPort.id) >= toPort.maximumConnections) {
      onStatus(`${toNode.label}.${toPort.label} has reached its connection limit`); return;
    }
    const edge: TopologyEdge = {
      id: `user-edge-${crypto.randomUUID()}`, from, fromPort: fromPort.id, to: target, toPort: toPort.id,
      portBinding: "explicit", net: fromPort.net || toPort.net || fromNode.net || toNode.net,
      kind: electricalClass(fromPort) === "reference" ? "return" : electricalClass(fromPort) === "control" ? "control" : domain === "si" ? "signal" : "power", origin: "user",
    };
    setModel({ ...model, edges: [...model.edges, edge] });
    onStatus(`Connected ${fromNode.label}.${fromPort.label} to ${toNode.label}.${toPort.label}`);
    return true;
  };
  const connectSelected = () => {
    if (selectedIds.size !== 2 || !selectedId) { onStatus("Select a source, then Ctrl-click one destination before choosing Connect selected"); return; }
    const from = [...selectedIds].find(id => id !== selectedId) ?? "";
    connectNodes(from, selectedId);
  };
  const startWire = (nodeId: string, requestedPortId?: string) => {
    const node = model.nodes.find(item => item.id === nodeId);
    if (!node) return;
    const ports = topologyPorts(node, domain);
    const port = ports.find(item => item.id === requestedPortId)
      ?? ports.find(item => item.side === "right" && ["output", "bidirectional", "passive"].includes(item.direction));
    if (!port || ["input", "control"].includes(port.direction)) { onStatus(`${node.label} has no compatible source port`); return; }
    setLinkFrom({ nodeId, portId: port.id });
    setWirePointer(topologyPortPoint(node, domain, port.id));
    selectOnly(nodeId);
    onStatus(`Wire started from ${node.label}.${port.label}. Click a compatible destination port`);
  };
  const finishWire = (nodeId: string, requestedPortId?: string) => {
    if (!linkFrom) { onStatus("Start at an OUT port, then click this IN port"); return; }
    if (linkFrom.nodeId === nodeId) { onStatus("A block cannot be wired to itself"); return; }
    if (connectNodes(linkFrom.nodeId, nodeId, linkFrom.portId, requestedPortId)) {
      setLinkFrom(null); setWirePointer(null);
    }
  };
  const autoExtract = () => {
    if (!board) { onStatus("Import a board before extracting topology"); return; }
    const extracted = extractTopologyFromBoard(board, domain);
    setExtractionPreview(extracted);
    onStatus(`Extraction preview ready: ${extracted.nodes.length} symbols. Review before applying to the sheet.`);
  };
  const importSource = (file: File) => {
    file.text().then(source => {
      try {
        const extracted = file.name.toLowerCase().endsWith(".xml")
          ? extractTopologyFromXmlNetlist(source, domain)
          : board ? extractTopologyFromBoard(board, domain, source) : emptyTopology(domain);
        if (!board && !file.name.toLowerCase().endsWith(".xml")) extracted.extraction.warnings = ["A KiCad board is required to resolve schematic symbols to routed nets."];
        setExtractionPreview(extracted);
        onStatus(`${file.name} cross-referenced into the ${domain.toUpperCase()} topology`);
      } catch (error) { onStatus(error instanceof Error ? error.message : "Topology import failed"); }
    });
  };
  const useForAnalysis = async () => {
    const topologyIssues = validateTopologyPorts(model);
    const structuralError = topologyIssues.find(issue => issue.severity === "error");
    if (structuralError) { onStatus(`${domain === "pi" ? "Power Tree" : "Channel Tree"} is invalid: ${structuralError.message}`); return; }
    if (domain === "si") {
      const inferred = model.edges.filter(edge => edge.portBinding !== "explicit").length;
      onUseForAnalysis(model, scenario.id, plan);
      if (inferred) onStatus(`Channel setup saved with ${inferred} inferred port connection${inferred === 1 ? "" : "s"}; review them before solver compilation`);
      return;
    }
    if (plan.status === "invalid") { onStatus(`Power tree cannot drive PI yet: ${plan.warnings[0] ?? "no valid rail jobs"}`); return; }
    if (board && isDesktopShell()) {
      const response = await runLocalWorker({ method: "validate_topology_circuit", params: { design: designForTopology(board), topology: model } });
      if (!response.ok || !response.result) { onStatus(response.error ?? "Power-tree circuit validation failed"); return; }
      const validation = response.result as { valid?: boolean; issues?: { message?: string }[]; counts?: { passive_elements?: number; unsupported_models?: number } };
      if (!validation.valid) { onStatus(`Power-tree model is blocked: ${validation.issues?.[0]?.message ?? "invalid pin or circuit model"}`); return; }
      onStatus(`Power tree validated: ${validation.counts?.passive_elements ?? 0} passive models ready; ${validation.counts?.unsupported_models ?? 0} device models remain explicitly gated`);
    }
    onUseForAnalysis(model, scenario.id, plan);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, select, textarea, [contenteditable='true']")) { event.stopPropagation(); return; }
      if ((event.ctrlKey || event.metaKey) && ["z", "y"].includes(event.key.toLowerCase())) { event.preventDefault(); event.stopImmediatePropagation(); (event.shiftKey || event.key.toLowerCase() === "y" ? onRedo : onUndo)?.(); return; }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") { event.preventDefault(); selectNodes(visibleNodes.map(node => node.id)); return; }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") { event.preventDefault(); duplicateSelected(); return; }
      if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); deleteSelected(); return; }
      if (event.key === "Escape") { setContextMenu(null); setLinkFrom(null); setWirePointer(null); setPendingDestructive(null); selectNodes([]); }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  useEffect(() => {
    if (fitPending && view === "diagram") { fitDiagram(); setFitPending(false); }
  }, [fitPending, model.nodes, view]);

  const applyGenerated = (generated: TopologyModel, replace: boolean) => {
    const next = replace ? generated : appendTopology(model, generated);
    setModel(next); selectOnly(next.nodes[replace ? 0 : model.nodes.length]?.id ?? "");
    setQuery(""); setView("diagram"); setFitPending(true); setLinkFrom(null); setWirePointer(null);
    setGeneratorOpen(false); setExtractionPreview(null);
    onStatus(`${generated.nodes.length} symbols and ${generated.edges.length} connections ${replace ? "replaced the sheet" : "added to the sheet"}. Select a symbol to review its model and terminals.`);
  };

  return <div className="modal-shade topology-shade"><div className={`topology-editor schematic-editor ${domain === "pi" ? "pi" : ""}`}>
    <header>
      <div><b>{domain === "pi" ? "POWER SCHEMATIC" : "SIGNAL SCHEMATIC"}</b><small>Define inputs → Review wiring → Assign models → {domain === "pi" ? "Use for analysis" : "Save channel setup"}</small></div>
      <button onClick={onClose} title="Close topology editor"><X size={17} /></button>
    </header>
    <div className="topology-toolbar">
      <button onClick={() => { setGeneratorOpen(true); setView("diagram"); }}><Plus size={14} /> Generate from inputs</button>
      <button onClick={onUndo} disabled={!onUndo} title="Undo (Ctrl+Z)"><Undo2 size={14} /></button>
      <button onClick={onRedo} disabled={!onRedo} title="Redo (Ctrl+Shift+Z)"><Redo2 size={14} /></button>
      <button onClick={autoExtract}><RefreshCw size={14} /> Extract from board</button>
      <label><FileInput size={14} /> Import schematic / netlist<input type="file" accept=".kicad_sch,.xml,.net" onChange={event => { const file = event.target.files?.[0]; if (file) importSource(file); event.target.value = ""; }} /></label>
      {domain === "pi" && <button className={pathWizardOpen ? "active" : ""} onClick={() => setPathWizardOpen(value => !value)} title="Manage source-to-load paths across multiple copper nets and series components"><Route size={14} /> Power paths</button>}
      <button onClick={arrangeDiagram} title="Arrange source-to-load"><LayoutGrid size={14} /> Arrange</button>
      <button disabled={selectedIds.size !== 2} onClick={connectSelected} title="Connect the first selected element to the most recently selected element"><Link2 size={14} /> Connect selected</button>
      <button className={linkFrom ? "active" : ""} disabled={!selectedId} onClick={() => linkFrom ? (setLinkFrom(null), setWirePointer(null), onStatus("Pending wire cancelled")) : startWire(selectedId)} title={linkFrom ? "Cancel the pending wire" : "Start a wire at the selected element; then click a compatible destination port"}><GitBranch size={14} /> {linkFrom ? "Cancel wire" : "Wire from selected"}</button>
      <button className={pendingDestructive === "reset" ? "danger-confirm" : ""} onClick={() => runDestructive("reset")} title="Reset to the topology opened in this workbench"><RotateCcw size={14} /> {pendingDestructive === "reset" ? "Confirm reset" : "Reset"}</button>
      <button className={pendingDestructive === "clear" ? "danger-confirm" : ""} onClick={() => runDestructive("clear")} title="Delete every element and connection from this sheet"><Trash2 size={14} /> {pendingDestructive === "clear" ? "Confirm clear" : "Clear"}</button>
      <div className="topology-view-switch">
        <button className={view === "diagram" ? "active" : ""} onClick={() => setView("diagram")} title="Block diagram"><GitBranch size={14} /></button>
        <button className={view === "text" ? "active" : ""} onClick={() => setView("text")} title="Synchronized text description"><FileText size={14} /></button>
        {domain === "pi" && <>
        <button className={view === "consumption" ? "active" : ""} onClick={() => setView("consumption")} title="Component consumption"><Table2 size={14} /></button>
        <button className={view === "rails" ? "active" : ""} onClick={() => setView("rails")} title="Rail summary"><BarChart3 size={14} /></button>
        </>}
      </div>
      <span className="topology-divider" />
      <label className="topology-filter"><Search size={13} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Filter node, net, reference" /></label>
      {domain === "pi" && <label className="topology-check"><input type="checkbox" checked={showReturns} onChange={event => setShowReturns(event.target.checked)} /> Ground returns</label>}
      <button onClick={() => { setInspectorOpen(value => !value); setFitPending(true); }}><Settings2 size={14} /> {inspectorOpen ? "Hide properties" : "Properties"}</button>
      <button className="topology-use" onClick={useForAnalysis}><Save size={14} /> {domain === "pi" ? "Use for analysis" : "Save channel setup"}</button>
      <button className={helpOpen ? "active" : ""} onClick={() => setHelpOpen(value => !value)} title={`${treeName} workflow help`}><CircleHelp size={14} /> Help</button>
    </div>
    {domain === "pi" && <div className={`topology-budget ${budget.status}`}>
      <label>OPERATING CASE<select value={scenario.id} onChange={event => setScenarioId(event.target.value)}>{scenarios.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <label>MULTIPLIER<input type="number" min="0" step="0.05" value={scenario.loadMultiplier} onChange={event => patchScenario(Number(event.target.value) || 0)} /></label>
      <button className="topology-add-scenario" onClick={addScenario} title="Add operating case"><Plus size={13} /></button>
      <div><span>SOURCE INPUT</span><b>{metric(budget.sourcePowerW, "W")}</b></div>
      <div><span>LOAD POWER</span><b>{metric(budget.loadPowerW, "W")}</b></div>
      <div><span>EST. LOSS</span><b>{metric(budget.lossW, "W")}</b></div>
      <div><span>EFFICIENCY</span><b>{budget.efficiencyPercent === undefined ? "-- %" : metric(budget.efficiencyPercent, "%", 1)}</b></div>
      <div className="topology-budget-state"><AlertTriangle size={13} /><span>{plan.status}</span><b>{plan.jobs.length} rail jobs | {plan.warnings.length} notices</b></div>
    </div>}
    <div className={`topology-layout ${inspectorOpen ? "" : "inspector-closed"}`}>
      <aside className="topology-palette"><label>ADD ELEMENT</label>{kinds[domain].map(item => {
        return <button key={item.kind} onClick={() => addNode(item.kind)} title={`${item.label}: ${item.help}`} aria-label={`Add ${item.label}. ${item.help}`}>{paletteSymbol(item.kind)}<span>{item.label}<small>{item.help}</small></span><Plus size={12} /></button>;
      })}<div className="topology-help"><b>CONNECT</b><p>Click a compatible source port, move the pending wire, then click the exact destination port. Escape cancels. Two selected blocks can also use <strong>Connect selected</strong> when their canonical ports are unambiguous.</p><button onClick={() => setHelpOpen(true)}><CircleHelp size={12} /> Full {treeName} workflow help</button></div></aside>
      <main ref={canvasRef} className={`topology-canvas ${view !== "diagram" ? "data-view" : ""}`}
        tabIndex={0}
        onContextMenu={event => {
          if (view !== "diagram" || (event.target as HTMLElement).closest(".topology-generator")) return;
          event.preventDefault();
          const rect = event.currentTarget.getBoundingClientRect();
          setContextMenu({ x: event.clientX - rect.left, y: event.clientY - rect.top });
        }}
        onWheel={event => {
          if (view !== "diagram" || (event.target as HTMLElement).closest(".topology-generator")) return;
          event.preventDefault();
          const rect = event.currentTarget.getBoundingClientRect(); const px = event.clientX - rect.left; const py = event.clientY - rect.top;
          setCamera(current => { const zoom = Math.max(0.2, Math.min(2.5, current.zoom * (event.deltaY < 0 ? 1.12 : 0.89))); const worldX = (px - current.x) / current.zoom; const worldY = (py - current.y) / current.zoom; return { x: px - worldX * zoom, y: py - worldY * zoom, zoom }; });
        }}
        onPointerDown={event => {
          if (event.button !== 0 && event.button !== 1) return;
          if ((event.target as HTMLElement).closest(".topology-node, .topology-camera, .topology-path-wizard, .topology-generator")) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          setContextMenu(null); setPendingDestructive(null);
          if (linkFrom && event.button === 0 && !event.altKey) {
            setLinkFrom(null); setWirePointer(null); onStatus("Pending wire cancelled");
            return;
          }
          if (event.button === 1 || event.altKey) {
            panRef.current = { pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY, x: camera.x, y: camera.y };
          } else {
            const point = canvasPoint(event.clientX, event.clientY); const startX = point.x; const startY = point.y;
            marqueeRef.current = { pointerId: event.pointerId, startX, startY, currentX: startX, currentY: startY };
            setMarquee({ x: startX, y: startY, width: 0, height: 0 });
          }
        }}
        onPointerMove={event => {
          if (linkFrom) setWirePointer(worldPoint(event.clientX, event.clientY));
          const pan = panRef.current;
          if (pan?.pointerId === event.pointerId) { setCamera(current => ({ ...current, x: pan.x + event.clientX - pan.clientX, y: pan.y + event.clientY - pan.clientY })); return; }
          const selection = marqueeRef.current;
          if (!selection || selection.pointerId !== event.pointerId || !canvasRef.current) return;
          const point = canvasPoint(event.clientX, event.clientY); selection.currentX = point.x; selection.currentY = point.y;
          setMarquee({ x: Math.min(selection.startX, selection.currentX), y: Math.min(selection.startY, selection.currentY), width: Math.abs(selection.currentX - selection.startX), height: Math.abs(selection.currentY - selection.startY) });
        }}
        onPointerUp={event => {
          if (panRef.current?.pointerId === event.pointerId) panRef.current = null;
          const selection = marqueeRef.current;
          if (selection?.pointerId === event.pointerId) {
            const left = (Math.min(selection.startX, selection.currentX) - camera.x) / camera.zoom; const right = (Math.max(selection.startX, selection.currentX) - camera.x) / camera.zoom;
            const top = (Math.min(selection.startY, selection.currentY) - camera.y) / camera.zoom; const bottom = (Math.max(selection.startY, selection.currentY) - camera.y) / camera.zoom;
            const dragged = Math.abs(selection.currentX - selection.startX) > 4 || Math.abs(selection.currentY - selection.startY) > 4;
            selectNodes(dragged ? visibleNodes.filter(node => node.x + topologyNodeWidth >= left && node.x <= right && node.y + topologyNodeHeight(node, domain) >= top && node.y <= bottom).map(node => node.id) : []);
            marqueeRef.current = null; setMarquee(null);
          }
        }}
        onPointerCancel={() => { panRef.current = null; marqueeRef.current = null; setMarquee(null); }}>
        {view === "diagram" && <div className="topology-camera" aria-label="Diagram navigation">
          <button onClick={() => zoomAtCenter(1.2)} title="Zoom in"><ZoomIn size={14} /></button>
          <button onClick={() => zoomAtCenter(0.83)} title="Zoom out"><ZoomOut size={14} /></button>
          <button onClick={fitDiagram} title="Fit diagram"><Maximize2 size={14} /></button>
          <span><Move size={12} /> {Math.round(camera.zoom * 100)}%</span>
        </div>}
        {generatorOpen && <TopologyGenerator domain={domain} board={board} onApply={applyGenerated} onClose={() => setGeneratorOpen(false)} />}
        {extractionPreview && <section className="topology-generator" role="dialog" aria-label="Review extracted schematic" onPointerDown={e => e.stopPropagation()}><header><b>Review extracted schematic</b><button onClick={() => setExtractionPreview(null)} aria-label="Close extraction preview">×</button></header><p>{extractionPreview.nodes.length} symbols · {extractionPreview.edges.length} connections. Inferred connections require review.</p><TopologyPreview model={extractionPreview} />{extractionPreview.extraction.warnings.map(w => <p key={w}>{w}</p>)}<button onClick={() => applyGenerated(extractionPreview, false)}>Add to sheet</button><button onClick={() => applyGenerated(extractionPreview, true)}>Replace sheet with preview</button></section>}
        {pathWizardOpen && domain === "pi" && <section className="topology-path-wizard">
          <header><div><b>POWER PATH / NET MANAGER</b><span>Build multiple source-to-load chains. Nets become rail segments; intervening parts become series elements; ground remains a shunt return.</span></div><button onClick={() => setPathWizardOpen(false)}><X size={14} /></button></header>
          <div><label>Input pad<select value={pathSourcePadId} onChange={event => setPathSourcePadId(event.target.value)}><option value="">Select input pad</option>{powerPads.map(pad => <option key={pad.id} value={pad.id}>{pad.net} | {pad.ref ?? "?"}.{pad.name} | {pad.layer}</option>)}</select></label>
          <label>Output pad<select value={pathLoadPadId} onChange={event => setPathLoadPadId(event.target.value)}><option value="">Select output pad</option>{powerPads.map(pad => <option key={pad.id} value={pad.id}>{pad.net} | {pad.ref ?? "?"}.{pad.name} | {pad.layer}</option>)}</select></label>
          <label>Sheet action<select value={pathMode} onChange={event => setPathMode(event.target.value as "add" | "replace")}><option value="add">Add path to sheet</option><option value="replace">Replace sheet</option></select></label>
          <button onClick={buildSelectedPath} disabled={!pathSourcePadId || !pathLoadPadId}><Route size={14} /> {pathMode === "add" ? "Add path" : "Build sheet"}</button></div>
          {pathGroups.length > 0 && <footer><b>LINKED PATHS</b>{pathGroups.map(group => <div key={group.id}><button onClick={() => { const node = model.nodes.find(item => item.pathGroupId === group.id); if (node) selectOnly(node.id); }}><span>{group.label}</span><small>{group.nets.size} net segments | {group.series} series parts</small></button><button onClick={() => removePathGroup(group.id)} title="Remove this path"><Trash2 size={13} /></button></div>)}</footer>}
        </section>}
        {helpOpen && <section className="topology-workflow-help" role="dialog" aria-label={`${treeName} workflow help`}>
          <header><div><b>{domain === "pi" ? "POWER TREE AND SPICE WORKFLOW" : "CHANNEL TREE WORKFLOW"}</b><span>{domain === "pi" ? "Build, connect, model, validate, and hand off a circuit-aware power path." : "Build a port-explicit source-to-sink channel setup without implying unavailable solver capability."}</span></div><button onClick={() => setHelpOpen(false)} title="Close help"><X size={14} /></button></header>
          {domain === "pi" ? <div className="topology-help-grid">
            <article><b>1. Build and select</b><ol><li>Extract the board/netlist, import a schematic, or add electrical elements from the palette.</li><li>Drag blocks to place them. Drag empty canvas to marquee-select; Ctrl-click adds or removes one block.</li><li>Right-click the canvas or a block for selection, duplicate, delete, arrange, fit, reset, and clear commands.</li></ol></article>
            <article><b>2. Connect power paths</b><ol><li>Click the exact source port on the upstream block. A dashed wire follows the cursor.</li><li>Click a compatible destination port to complete the directed connection. Press Escape or click blank canvas to cancel.</li><li>Use the port editor for multiple outputs, returns, controls, connector pins, or harness conductors.</li></ol></article>
            <article><b>3. Configure SPICE models</b><ol><li>Select an element and assign its <strong>Simulation model</strong>: R, L, C, diode, MOSFET, source, load, subcircuit, or behavioral block.</li><li>Open <strong>Model assistant</strong>. Enter primitive/parasitic values or a reviewed model link, then map every participating component pin to input, output, return, control, passive, or unused.</li><li>Choose <strong>ngspice</strong> for an explicit circuit or <strong>Geometry parasitics + ngspice</strong> for staged co-simulation. The geometry stage extracts interconnect parasitics; ngspice evaluates the composed circuit.</li></ol></article>
            <article><b>4. Validate and run</b><ol><li>Assign source voltage and load current/power for the active operating case. Add more cases for derating or corner analysis.</li><li>Choose <strong>Use for analysis</strong>. SPIKE validates topology, pin mapping, model readiness, and produces rail jobs for PI setup.</li><li>Run the generated PI or circuit jobs from their analysis workspace. Unsupported device models remain visibly blocked rather than replaced by invented behavior.</li></ol></article>
          </div> : <div className="topology-help-grid">
            <article><b>1. Build the channel</b><ol><li>Add drivers, routed channels, connectors, cables, terminations, and receivers.</li><li>Generic blocks start with neutral ports; choose a differential template only when the signaling really is differential.</li><li>Add or remove ports for lanes, bus bits, references, shields, sidebands, and package interfaces.</li></ol></article>
            <article><b>2. Bind exact ports</b><ol><li>Name each port and assign direction, electrical kind, side, net, lane, and differential-pair identity.</li><li>Wire the exact source and destination ports. Inferred legacy bindings remain visibly identified in the text description.</li><li>Connection limits prevent accidentally attaching multiple links to a single-use terminal.</li></ol></article>
            <article><b>3. Review as text</b><ol><li>Open the Text view for a deterministic description of blocks, ports, models, and connections.</li><li>Copy the readable text for reviews or diffs; copy JSON for lossless machine round-trip.</li><li>The text form is read-only and cannot become a second conflicting topology source.</li></ol></article>
            <article><b>4. Save setup honestly</b><ol><li>Save the channel setup after structural validation.</li><li>Inferred port connections, missing models, and unavailable numerical stages remain explicit gates.</li><li>A saved Channel Tree is not yet an SI compliance result or proof of solver readiness.</li></ol></article>
          </div>}
          <footer><kbd>Ctrl+A</kbd> select all <kbd>Ctrl+D</kbd> duplicate <kbd>Delete</kbd> remove <kbd>Esc</kbd> cancel/clear selection <span>Middle-drag or Alt-drag pans; wheel zooms.</span></footer>
        </section>}
        {marquee && <div className="topology-marquee" style={{ left: marquee.x, top: marquee.y, width: marquee.width, height: marquee.height }} />}
        {contextMenu && <div className="topology-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }} onPointerDown={event => event.stopPropagation()} onContextMenu={event => event.preventDefault()}>
          <button onClick={() => { selectNodes(visibleNodes.map(node => node.id)); setContextMenu(null); }}>Select all <kbd>Ctrl+A</kbd></button>
          <button disabled={!selectedIds.size} onClick={() => { duplicateSelected(); setContextMenu(null); }}><Copy size={13} /> Duplicate selected <kbd>Ctrl+D</kbd></button>
          <button disabled={!selectedIds.size} onClick={() => { deleteSelected(); setContextMenu(null); }}><Trash2 size={13} /> Delete selected <kbd>Del</kbd></button>
          <button disabled={selectedIds.size !== 2} onClick={() => { connectSelected(); setContextMenu(null); }}><Link2 size={13} /> Connect selected</button>
          {contextMenu.nodeId && linkFrom && linkFrom.nodeId !== contextMenu.nodeId && <button onClick={() => { finishWire(contextMenu.nodeId!); setContextMenu(null); }}><Link2 size={13} /> Finish wire at this block</button>}
          {contextMenu.nodeId && !linkFrom && <button onClick={() => { startWire(contextMenu.nodeId!); setContextMenu(null); }}><GitBranch size={13} /> Start wire from this block</button>}
          <hr />
          <button onClick={() => { arrangeDiagram(); setContextMenu(null); }}><LayoutGrid size={13} /> Arrange diagram</button>
          <button onClick={() => { fitDiagram(); setContextMenu(null); }}><Maximize2 size={13} /> Fit diagram</button>
          <button onClick={() => { runDestructive("reset"); setContextMenu(null); }}><RotateCcw size={13} /> Reset canvas</button>
          <button className="danger" onClick={() => { runDestructive("clear"); setContextMenu(null); }}><Trash2 size={13} /> Clear canvas</button>
          <button onClick={() => { setHelpOpen(true); setContextMenu(null); }}><CircleHelp size={13} /> {treeName} workflow help</button>
        </div>}
        {view === "diagram" ? <div className="topology-surface" style={{ width, height, transform: `translate(${camera.x}px, ${camera.y}px) scale(${camera.zoom})` }}>
          <svg width={width} height={height}><defs><marker id="topology-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" /></marker></defs>{visibleEdges.map(edge => {
            const route = schematicWire(edge, visibleNodes, domain);
            if (!route) return null;
            const connected = visibleEdges.filter(other => other.from === edge.from && other.fromPort === edge.fromPort).length > 1;
            return <g key={edge.id} className={`topology-edge ${edge.kind}`}><title>{edge.net || edge.kind} · {edge.portBinding === "explicit" ? "Explicit connection" : "Inferred connection — review"}</title><path d={route.d} />{connected && <circle cx={route.a.x} cy={route.a.y} r="3" fill="currentColor" />}{edge.net && <text x={route.labelX} y={route.labelY} textAnchor="middle">{edge.net}</text>}</g>;
          })}{linkFrom && wirePointer && (() => {
            const source = model.nodes.find(node => node.id === linkFrom.nodeId);
            if (!source) return null;
            const start = topologyPortPoint(source, domain, linkFrom.portId); const startX = start.x; const startY = start.y;
            return <path className="topology-pending-wire" d={`M ${startX} ${startY} H ${(startX + wirePointer.x) / 2} V ${wirePointer.y} H ${wirePointer.x}`} />;
          })()}</svg>
          {visibleNodes.map(node => {
            const nodeBudget = budget.nodes[node.id];
            const overloaded = nodeBudget && node.maxCurrentA !== undefined && nodeBudget.currentA > node.maxCurrentA;
            const enabled = node.enabled !== false && node.operatingPoints?.[scenario.id]?.enabled !== false;
            return <button key={node.id} data-node-id={node.id} onDoubleClick={() => setInspectorOpen(true)} className={`topology-node ${selectedIds.has(node.id) ? "selected" : ""} ${linkFrom?.nodeId === node.id ? "link-source" : ""} ${overloaded ? "overloaded" : ""} ${!enabled ? "disabled" : ""}`} style={{ left: node.x, top: node.y, height: topologyNodeHeight(node, domain) }} onMouseEnter={() => previewNode(node)} onMouseLeave={() => previewNode(undefined)} onClick={event => { if (linkFrom) { finishWire(node.id); return; } if (event.ctrlKey || event.metaKey) { const next = new Set(selectedIds); next.has(node.id) ? next.delete(node.id) : next.add(node.id); selectNodes(next, node.id); } else if (!selectedIds.has(node.id)) selectOnly(node.id); }}
              onContextMenu={event => { event.preventDefault(); event.stopPropagation(); if (!selectedIds.has(node.id)) selectOnly(node.id); const rect = canvasRef.current?.getBoundingClientRect(); if (rect) setContextMenu({ x: event.clientX - rect.left, y: event.clientY - rect.top, nodeId: node.id }); }}
              onPointerDown={event => { if (event.button !== 0 || (event.target as HTMLElement).closest("[data-topology-port]")) return; event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId); const ids = selectedIds.has(node.id) ? selectedIds : new Set([node.id]); if (!selectedIds.has(node.id)) selectOnly(node.id); dragRef.current = { pointerId: event.pointerId, nodeId: node.id, clientX: event.clientX, clientY: event.clientY, starts: new Map(model.nodes.filter(item => ids.has(item.id)).map(item => [item.id, { x: item.x, y: item.y }])) }; setSelectedId(node.id); setContextMenu(null); }}
              onPointerMove={event => { const drag = dragRef.current; if (!drag || drag.pointerId !== event.pointerId || drag.nodeId !== node.id) return; const dx = (event.clientX - drag.clientX) / camera.zoom; const dy = (event.clientY - drag.clientY) / camera.zoom; setModel({ ...model, nodes: model.nodes.map(item => { const start = drag.starts.get(item.id); return start ? { ...item, x: Math.round((start.x + dx) / 5) * 5, y: Math.round((start.y + dy) / 5) * 5 } : item; }) }, !drag.recorded); drag.recorded = true; }}
              onPointerUp={event => { if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null; }}>
              <span className="topology-port-stack input">{topologyPorts(node, domain).filter(port => port.side === "left").map((port, index, ports) => <span key={port.id} style={{ top: `${(index + 1) * 100 / (ports.length + 1)}%` }} data-topology-port="input" data-port-id={port.id} role="button" tabIndex={0} className={`topology-port input ${port.direction}`} onPointerDown={event => event.stopPropagation()} onClick={event => { event.stopPropagation(); linkFrom ? finishWire(node.id, port.id) : startWire(node.id, port.id); }} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") linkFrom ? finishWire(node.id, port.id) : startWire(node.id, port.id); }} title={`${port.label}: ${port.direction} ${port.kind} port on ${node.label}`}><i /><small>{port.label}</small></span>)}</span>
              <CircuitSymbol node={node} size={62} /><span className="topology-node-copy"><b>{node.label}</b><small>{node.net || node.value || node.kind}</small><em>{topologyPorts(node, domain).length} ports{domain === "pi" && nodeBudget ? ` | ${nodeBudget.voltageV === undefined ? "-- V" : metric(nodeBudget.voltageV, "V")} | ${metric(nodeBudget.currentA, "A")}${nodeBudget.lossW > 0 ? ` | ${metric(nodeBudget.lossW, "W")} loss` : ""}` : ""}</em></span>
              <span className="topology-port-stack output">{topologyPorts(node, domain).filter(port => port.side === "right").map((port, index, ports) => <span key={port.id} style={{ top: `${(index + 1) * 100 / (ports.length + 1)}%` }} data-topology-port="output" data-port-id={port.id} role="button" tabIndex={0} className={`topology-port output ${port.direction}`} onPointerDown={event => event.stopPropagation()} onClick={event => { event.stopPropagation(); linkFrom ? finishWire(node.id, port.id) : startWire(node.id, port.id); }} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") linkFrom ? finishWire(node.id, port.id) : startWire(node.id, port.id); }} title={`${port.label}: ${port.direction} ${port.kind} port on ${node.label}`}><i /><small>{port.label}</small></span>)}</span>
            </button>;
          })}
          {!visibleNodes.length && <div className="topology-empty"><Network size={28} /><b>No topology nodes</b><span>Generate a schematic from your inputs, extract the board, or place a symbol.</span><button onClick={() => setGeneratorOpen(true)}>Generate from inputs</button></div>}
        </div> : view === "text" ? <section className="topology-text-panel" aria-label={`${domain === "pi" ? "Power Tree" : "Channel Tree"} text equivalent`}>
          <header><div><b>READ-ONLY TEXT EQUIVALENT</b><span>Synchronized from the authoritative topology JSON; intended for review, accessibility, copying, and diffs.</span></div><div><button onClick={() => void copyTopology("text")}><Copy size={13} /> Copy text</button><button onClick={exportTopologyText}><Download size={13} /> Export text</button><button onClick={() => void copyTopology("json")}><Copy size={13} /> Copy JSON</button></div></header>
          <pre tabIndex={0}>{textEquivalent}</pre>
          <details><summary>Accessible topology outline</summary><ol>{[...model.nodes].sort((a, b) => a.label.localeCompare(b.label)).map(node => <li key={node.id}><b>{node.label}</b> — {node.kind}. Ports: {topologyPorts(node, domain).map(port => `${port.label} (${port.direction} ${port.kind})`).join(", ")}.</li>)}</ol><h4>Connections</h4><ol>{model.edges.map(edge => { const from = model.nodes.find(node => node.id === edge.from); const to = model.nodes.find(node => node.id === edge.to); const fromPort = from ? topologyPorts(from, domain).find(port => port.id === edge.fromPort) : undefined; const toPort = to ? topologyPorts(to, domain).find(port => port.id === edge.toPort) : undefined; return <li key={edge.id}>{from?.label ?? edge.from}.{fromPort?.label ?? "unspecified"} to {to?.label ?? edge.to}.{toPort?.label ?? "unspecified"}, {edge.kind}{edge.net ? ` on ${edge.net}` : ""}.</li>; })}</ol></details>
        </section> : view === "consumption" ? <div className="topology-data-panel">
          <header><div><b>COMPONENT CONSUMPTION</b><span>{scenario.label} operating case</span></div><strong>{loads.length} loads</strong></header>
          <table className="topology-table"><thead><tr><th>Use</th><th>Reference / load</th><th>Rail</th><th>Current (A)</th><th>Power (W)</th><th>Model</th><th>Status</th></tr></thead><tbody>{loads.map(node => {
            const point = node.operatingPoints?.[scenario.id]; const value = budget.nodes[node.id];
            const railNet = node.net ?? model.edges.find(edge => edge.to === node.id && edge.kind === "power")?.net ?? "Unassigned";
            return <tr key={node.id} className={selectedId === node.id ? "selected" : ""} onMouseEnter={() => previewNode(node)} onMouseLeave={() => previewNode(undefined)} onClick={() => selectOnly(node.id)}>
              <td><input type="checkbox" checked={node.enabled !== false && point?.enabled !== false} onClick={event => event.stopPropagation()} onChange={event => patchOperatingPoint(node, { enabled: event.target.checked })} /></td>
              <td><b>{node.ref || node.label}</b><span>{node.value || node.label}</span></td><td>{railNet}</td>
              <td><input type="number" min="0" step="0.01" value={point?.currentA ?? ""} placeholder={(value?.currentA ?? 0).toFixed(3)} onClick={event => event.stopPropagation()} onChange={event => patchOperatingPoint(node, { currentA: optionalNumber(event.target.value) })} /></td>
              <td><input type="number" min="0" step="0.1" value={point?.powerW ?? ""} placeholder={(value?.outputPowerW ?? 0).toFixed(3)} onClick={event => event.stopPropagation()} onChange={event => patchOperatingPoint(node, { powerW: optionalNumber(event.target.value) })} /></td>
              <td>{node.simulationModel || "Unassigned"}</td><td><span className={`topology-state ${value?.outputPowerW ? "ready" : "needs_setup"}`}>{value?.outputPowerW ? "Ready" : "Needs load"}</span></td>
            </tr>;
          })}</tbody></table>
        </div> : <div className="topology-data-panel">
          <header><div><b>RAIL ANALYSIS PLAN</b><span>Geometry-resolved PI jobs generated from the selected scenario</span></div><strong>{plan.jobs.filter(job => job.status === "ready").length} / {plan.jobs.length} ready</strong></header>
          <table className="topology-table"><thead><tr><th>Rail / net</th><th>Voltage</th><th>Current</th><th>Load power</th><th>Loads</th><th>Terminals</th><th>Status</th></tr></thead><tbody>{rails.map(rail => {
            const node = model.nodes.find(item => item.id === rail.nodeId); const job = plan.jobs.find(item => item.railNodeId === rail.nodeId);
            return <tr key={rail.nodeId} className={selectedId === rail.nodeId ? "selected" : ""} onMouseEnter={() => previewNode(node)} onMouseLeave={() => previewNode(undefined)} onClick={() => selectOnly(rail.nodeId)}>
              <td><b>{rail.net}</b><span>{node?.label}</span></td><td>{rail.voltageV === undefined ? "-- V" : metric(rail.voltageV, "V")}</td><td>{metric(rail.currentA, "A")}</td><td>{metric(rail.powerW, "W")}</td><td>{rail.downstreamLoadIds.length}</td><td>{job?.sourceNodeIds.length ?? 0} source / {job?.loadNodeIds.length ?? 0} load</td><td><span className={`topology-state ${job?.status ?? "needs_setup"}`}>{job?.status.replace("_", " ") ?? "needs setup"}</span></td>
            </tr>;
          })}</tbody></table>
        </div>}
      </main>
      <aside className="topology-inspector"><label>ELEMENT PROPERTIES</label>{selected ? <>
        <div className="topology-kind"><span>{selected.kind.replace("_", " ")}</span><small>{selected.origin}</small></div>
        <label>Name<input value={selected.label} onChange={event => patchSelected({ label: event.target.value })} /></label>
        <label>Reference<input value={selected.ref ?? ""} onChange={event => patchSelected({ ref: event.target.value })} /></label>
        <label>Net<input list="schematic-net-options" value={selected.net ?? ""} onChange={event => patchSelected({ net: event.target.value })} placeholder="Enter or choose a net" /><datalist id="schematic-net-options">{[...new Set(Object.values(board?.nets ?? {}).filter(Boolean))].sort().map(net => <option key={net} value={net} />)}</datalist></label>
        <label>Model / value<input value={selected.value ?? ""} onChange={event => patchSelected({ value: event.target.value, circuitModel: { ...selected.circuitModel, value: event.target.value } })} /></label>
        <section className="topology-port-editor">
          <header><div><b>BLOCK PORTS</b><span>{topologyPorts(selected, domain).length} explicit or migrated ports</span></div><button onClick={addSelectedPort}><Plus size={12} /> Add</button></header>
          <div className="topology-port-templates"><button onClick={() => replaceSelectedPorts("generic")}>Generic template</button>{domain === "si" && <button onClick={() => replaceSelectedPorts("differential")}>Differential template</button>}</div>
          {topologyPorts(selected, domain).map(port => <article key={port.id}>
            <div><code>{port.id}</code><button onClick={() => removeSelectedPort(port.id)} title={`Remove ${port.label}`}><Trash2 size={11} /></button></div>
            <label>Label<input value={port.label} onChange={event => patchSelectedPort(port.id, { label: event.target.value })} /></label>
            <label>Direction<select value={port.direction} onChange={event => patchSelectedPort(port.id, { direction: event.target.value as TopologyPort["direction"] })}><option value="input">Input</option><option value="output">Output</option><option value="bidirectional">Bidirectional</option><option value="passive">Passive</option><option value="reference">Reference</option><option value="control">Control</option></select></label>
            <label>Electrical kind<select value={port.kind} onChange={event => patchSelectedPort(port.id, { kind: event.target.value as TopologyPort["kind"] })}><option value="power">Power</option><option value="return">Return</option><option value="signal">Signal</option><option value="reference">Reference</option><option value="control">Control</option><option value="shield">Shield</option></select></label>
            <label>Side<select value={port.side} onChange={event => patchSelectedPort(port.id, { side: event.target.value as TopologyPort["side"] })}><option value="left">Left</option><option value="right">Right</option></select></label>
            <label>Net<input value={port.net ?? ""} placeholder="Optional exact net" onChange={event => patchSelectedPort(port.id, { net: event.target.value || undefined })} /></label>
            {domain === "si" && <><label>Lane<input value={port.lane ?? ""} placeholder="lane0 / DQ0" onChange={event => patchSelectedPort(port.id, { lane: event.target.value || undefined })} /></label><label>Differential pair<input value={port.pair ?? ""} placeholder="pair0" onChange={event => patchSelectedPort(port.id, { pair: event.target.value || undefined })} /></label></>}
            <label>Connection limit<input type="number" min="1" step="1" value={port.maximumConnections ?? ""} placeholder="Unlimited" onChange={event => patchSelectedPort(port.id, { maximumConnections: optionalNumber(event.target.value) })} /></label>
          </article>)}
        </section>
        {domain === "pi" && <>
          <label className="topology-enabled"><input type="checkbox" checked={selected.enabled !== false && selected.operatingPoints?.[scenario.id]?.enabled !== false} onChange={event => patchOperatingPoint(selected, { enabled: event.target.checked })} /> Include in {scenario.label}</label>
          {(selected.kind === "source" || selected.kind === "regulator" || selected.kind === "transformer" || selected.kind === "rail" || selected.kind === "return") && <label>{selected.kind === "return" ? "Local reference (V)" : "Output voltage (V)"}<input type="number" min="0" step="0.01" value={selected.voltageV ?? ""} onChange={event => patchSelected({ voltageV: optionalNumber(event.target.value) })} /></label>}
          {selected.kind === "load" && <><label>{scenario.label} current (A)<input type="number" min="0" step="0.01" value={selected.operatingPoints?.[scenario.id]?.currentA ?? ""} placeholder={selected.loadCurrentA?.toString() ?? "Not assigned"} onChange={event => patchOperatingPoint(selected, { currentA: optionalNumber(event.target.value) })} /></label><label>{scenario.label} power (W)<input type="number" min="0" step="0.1" value={selected.operatingPoints?.[scenario.id]?.powerW ?? ""} placeholder={selected.loadPowerW?.toString() ?? "Not assigned"} onChange={event => patchOperatingPoint(selected, { powerW: optionalNumber(event.target.value) })} /></label></>}
          {(selected.kind === "regulator" || selected.kind === "transformer") && <label>Efficiency (%)<input type="number" min="0.1" max="100" step="0.1" value={selected.efficiencyPercent ?? ""} placeholder="90" onChange={event => patchSelected({ efficiencyPercent: optionalNumber(event.target.value) })} /></label>}
          {(selected.kind === "passive" || selected.kind === "connector" || selected.kind === "harness") && <label>Series resistance (ohm)<input type="number" min="0" step="0.001" value={selected.resistanceOhm ?? ""} onChange={event => patchSelected({ resistanceOhm: optionalNumber(event.target.value) })} /></label>}
          <label>Maximum current (A)<input type="number" min="0" step="0.1" value={selected.maxCurrentA ?? ""} onChange={event => patchSelected({ maxCurrentA: optionalNumber(event.target.value) })} /></label>
          <label>Placement<select value={selected.orientation ?? "block"} onChange={event => { const orientation = event.target.value as TopologyNode["orientation"]; patchSelected({ orientation, circuitModel: selected.circuitModel ? { ...selected.circuitModel, orientation: orientation === "shunt" ? "shunt" : "series" } : undefined }); }}><option value="series">Series path</option><option value="shunt">Shunt element</option><option value="block">Source / load block</option></select></label>
          <label>Simulation model<select value={selected.simulationModel ?? ""} onChange={event => { const simulationModel = event.target.value; const primitive = ["resistor", "inductor", "capacitor"].includes(simulationModel) ? simulationModel as "resistor" | "inductor" | "capacitor" : undefined; patchSelected({ simulationModel, solverPolicy: primitive ? "staged_hybrid" : ["spice_subcircuit", "mosfet", "diode", "behavioral_block"].includes(simulationModel) ? "ngspice" : selected.solverPolicy, circuitModel: primitive ? { ...selected.circuitModel, primitive, type: primitive, value: selected.value, orientation: selected.orientation === "shunt" ? "shunt" : "series" } : selected.circuitModel }); }}><option value="">Unassigned</option><option value="resistor">Resistor (R)</option><option value="inductor">Inductor / ferrite (L)</option><option value="capacitor">Capacitor (C)</option><option value="diode">Diode (D)</option><option value="mosfet">MOSFET / transistor (Q)</option><option value="dc_source">DC source</option><option value="isolated_transformer">Isolated transformer boundary</option><option value="pwm_source">PWM source</option><option value="constant_current">Constant-current load</option><option value="constant_power">Constant-power load</option><option value="resistive_load">Resistive load</option><option value="spice_subcircuit">SPICE subcircuit</option><option value="behavioral_block">Behavioral model</option></select></label>
          {(selected.kind === "transformer" || selected.kind === "return") && <label>Isolation domain<input value={selected.isolationDomain ?? ""} placeholder="secondary-1" onChange={event => patchSelected({ isolationDomain: event.target.value })} /></label>}
          <label>Model link<input value={selected.modelLink ?? ""} placeholder="Library URI or local model ID" onChange={event => patchSelected({ modelLink: event.target.value })} /></label>
          {(selected.kind === "source" || selected.kind === "load") && selectedPads.length > 0 && <label>Terminal pad<select value={selected.terminalPadId ?? ""} onChange={event => patchSelected({ terminalPadId: event.target.value })}><option value="">Automatic first matching pad</option>{selectedPads.map(pad => <option key={pad.id} value={pad.id}>{selected.ref}.{pad.name} | {pad.net ?? "no net"} | {pad.layers.join(", ")}</option>)}</select></label>}
          <button className={`topology-model-assistant-button ${modelAssistantOpen ? "active" : ""}`} onClick={() => setModelAssistantOpen(value => !value)}><Settings2 size={13} /> Model assistant</button>
          {modelAssistantOpen && <section className="topology-model-assistant">
            <header><b>PIN AND DEVICE MODEL</b><span className={modelReady ? "ready" : "needs_setup"}>{modelReady ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}{modelReady ? "Configured" : "Needs model data"}</span></header>
            <p>Primitive R/L/C values can enter the staged geometry + ngspice flow. Nonlinear devices require a reviewed model link and explicit pin mapping.</p>
            {activeModelFields.map(field => <label key={field.key}>{field.label}<input value={String(selected.modelParameters?.[field.key] ?? "")} placeholder={field.placeholder} onChange={event => patchModelParameter(field.key, event.target.value)} /></label>)}
            {selectedPads.length > 0 ? <table><thead><tr><th>Pin</th><th>Net</th><th>Role</th></tr></thead><tbody>{selectedPads.map(pad => <tr key={pad.id}><td>{pad.name}</td><td title={pad.net}>{pad.net ?? "-"}</td><td><select value={selected.pinRoles?.[pad.name] ?? (pad.net && groundNet.test(pad.net) ? "return" : "unused")} onChange={event => patchPinRole(pad.name, event.target.value as TopologyPinRole)}><option value="input">Input</option><option value="output">Output</option><option value="return">Return</option><option value="control">Control</option><option value="passive">Passive terminal</option><option value="unused">Unused</option></select></td></tr>)}</tbody></table> : <p>No board pads resolve to this reference. Assign a component reference or use a subcircuit model without board binding.</p>}
            <label>Execution path<select value={selected.solverPolicy ?? "staged_hybrid"} onChange={event => patchSelected({ solverPolicy: event.target.value as TopologyNode["solverPolicy"] })}><option value="geometry">Geometry solver only</option><option value="ngspice">ngspice circuit model</option><option value="staged_hybrid">Geometry parasitics + ngspice</option></select></label>
          </section>}
        </>}
        <label>Type<select value={selected.kind} onChange={event => { const kind = event.target.value as TopologyNodeKind; setModel({ ...model, nodes: model.nodes.map(node => node.id === selected.id ? { ...node, kind, ports: defaultTopologyPorts(kind, domain, node.orientation) } : node), edges: model.edges.filter(edge => edge.from !== selected.id && edge.to !== selected.id) }); onStatus(`${selected.label} type changed; ports were reset and incident connections removed for review`); }}>{kinds[domain].map(item => <option key={item.kind} value={item.kind}>{item.label}</option>)}</select></label>
        <button className="topology-delete" onClick={deleteSelected}><Trash2 size={13} /> Delete element</button>
        <section className="topology-connection-list"><b>CONNECTIONS</b>{model.edges.filter(edge => edge.from === selected.id || edge.to === selected.id).map(edge => <div key={edge.id}><span>{model.nodes.find(node => node.id === edge.from)?.label} → {model.nodes.find(node => node.id === edge.to)?.label}<small>{edge.fromPort} → {edge.toPort}{edge.net ? ` · ${edge.net}` : ""}</small></span><button title="Remove connection" aria-label={`Remove connection from ${model.nodes.find(node => node.id === edge.from)?.label} to ${model.nodes.find(node => node.id === edge.to)?.label}`} onClick={() => setModel({ ...model, edges: model.edges.filter(item => item.id !== edge.id) })}><X size={13} /></button></div>)}</section>
      </> : <p>Select a topology element to edit it.</p>}
      <div className="topology-stats"><b>MODEL STATUS</b><span>{model.nodes.length} elements</span><span>{model.edges.length} connections</span>{(domain === "pi" ? plan.warnings : model.extraction.warnings).map(warning => <p key={warning}>{warning}</p>)}</div></aside>
    </div>
  </div></div>;
}
