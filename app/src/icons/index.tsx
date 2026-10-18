// SPDX-License-Identifier: Apache-2.0
import { createElement, forwardRef, type SVGProps } from "react";
import type { LucideIcon, LucideProps } from "lucide-react";

export * from "lucide-react";
export type { LucideIcon, LucideProps } from "lucide-react";

type IconTag = "path" | "circle" | "rect" | "line" | "polyline" | "polygon" | "ellipse";
type IconNode = readonly [IconTag, Readonly<Record<string, string | number>>];
export type WorkbenchIconCategory = "Electrical" | "RF / SI" | "Thermal" | "Geometry" | "Results" | "Application";
export type WorkbenchIconMeta = { name: string; description: string; category: WorkbenchIconCategory; icon: LucideIcon };
const inventory: WorkbenchIconMeta[] = [];

function defineIcon(name: string, description: string, category: WorkbenchIconCategory, nodes: readonly IconNode[]): LucideIcon {
  const Icon = forwardRef<SVGSVGElement, LucideProps>(({ color = "currentColor", size = 24, strokeWidth = 1.8, absoluteStrokeWidth, children, ...props }, ref) => {
    const label = props["aria-label"];
    const resolvedStroke = absoluteStrokeWidth && typeof size === "number" ? Number(strokeWidth) * 24 / size : strokeWidth;
    const accessibility: SVGProps<SVGSVGElement> = label || props["aria-labelledby"] ? { role: "img" } : { "aria-hidden": true };
    return <svg ref={ref} xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={resolvedStroke} strokeLinecap="round" strokeLinejoin="round" {...accessibility} {...props}>
      {label ? <title>{String(label)}</title> : null}
      {nodes.map(([tag, attributes], index) => createElement(tag, { ...attributes, key: `${name}-${index}` }))}
      {children}
    </svg>;
  }) as LucideIcon;
  Icon.displayName = name;
  inventory.push({ name, description, category, icon: Icon });
  return Icon;
}

const p = (d: string): IconNode => ["path", { d }];
const c = (cx: number, cy: number, r: number): IconNode => ["circle", { cx, cy, r }];
const l = (x1: number, y1: number, x2: number, y2: number): IconNode => ["line", { x1, y1, x2, y2 }];
const r = (x: number, y: number, width: number, height: number, rx = 1): IconNode => ["rect", { x, y, width, height, rx }];

export const Activity = defineIcon("Activity", "Measured waveform and live engineering activity", "Results", [p("M3 13h3l2-6 4 11 3-8 2 3h4")]);
export const CircuitBoard = defineIcon("CircuitBoard", "PCB outline with routed pads and vias", "Geometry", [r(3, 4, 18, 16, 2), c(7, 8, 1), c(17, 16, 1), p("M8 8h4v4h4v4M7 16h4M17 8h-2")]);
export const Grid3X3 = defineIcon("Grid3X3", "Structured engineering mesh cells", "Geometry", [p("M4 4h16v16H4zM9 4v16M15 4v16M4 9h16M4 15h16"), c(15, 9, 1)]);
export const Crosshair = defineIcon("Crosshair", "Field or voltage probe target", "Results", [c(12, 12, 6), c(12, 12, 1.5), p("M12 2v4M12 18v4M2 12h4M18 12h4")]);
export const Omega = defineIcon("Omega", "Impedance and resistance quantity", "Electrical", [p("M7 19h-3v-3h4c-2-1.4-3-3.4-3-5.7A7 7 0 0 1 19 10.3c0 2.3-1 4.3-3 5.7h4v3h-3M9 19h6")]);
export const ThermometerSun = defineIcon("ThermometerSun", "Thermal state and heat exposure", "Thermal", [p("M8 5a2 2 0 0 1 4 0v8.5a4 4 0 1 1-4 0zM10 9v7"), c(18, 6, 2), p("M18 1v1M18 10v1M13 6h1M22 6h1M15 3l-.8-.8M21.8 9.8 21 9")]);
export const Cpu = defineIcon("Cpu", "Solver compute engine", "Application", [r(6, 6, 12, 12, 2), r(9, 9, 6, 6, 1), p("M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4")]);
export const Microchip = defineIcon("Microchip", "Circuit and SPICE model", "Electrical", [r(7, 5, 10, 14, 2), p("M10 9h4v6h-4zM3 8h4M3 12h4M3 16h4M17 8h4M17 12h4M17 16h4")]);
export const Plug = defineIcon("Plug", "RF or electrical port", "Electrical", [p("M8 4v6M16 4v6M6 10h12v2a6 6 0 0 1-6 6v3M9 7h6")]);
export const PlugZap = defineIcon("PlugZap", "Driven source terminal", "Electrical", [p("M7 3v6M15 3v6M5 9h12v2a6 6 0 0 1-6 6v4M14 12l-3 4h3l-2 3")]);
export const ChartSpline = defineIcon("ChartSpline", "Frequency response curve", "Results", [p("M4 4v16h17M6 16c3-7 5 2 8-5s4-4 7-1"), c(14, 11, 1)]);
// Visibility controls stay distinct from the electrical signal-eye symbol.
export const Visibility = defineIcon("Visibility", "Show a hidden tool or control", "Application", [p("M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12"), c(12,12,3)]);
export const VisibilityOff = defineIcon("VisibilityOff", "Hide a tool and retain its state", "Application", [p("m3 3 18 18M9.5 6.3A13 13 0 0 1 12 6c6.5 0 10 6 10 6a19 19 0 0 1-3.1 3.5M6.2 6.8A19 19 0 0 0 2 12s3.5 6 10 6c1.9 0 3.6-.5 5-1.2M10 10a3 3 0 0 0 4 4")]);
export const SignalEye = defineIcon("SignalEye", "Signal integrity eye diagram", "RF / SI", [p("M2.5 12s3.5-5 9.5-5 9.5 5 9.5 5-3.5 5-9.5 5-9.5-5-9.5-5z"), c(12, 12, 2.3), p("M8 8l8 8M16 8l-8 8")]);
export const Layers3 = defineIcon("Layers3", "PCB stackup and material layers", "Geometry", [p("M3 8l9-5 9 5-9 5zM5 12l7 4 7-4M5 16l7 4 7-4")]);
// The generic visibility name always uses the conventional eye glyph.
export const Eye = Visibility;
export const Boxes = defineIcon("Boxes", "MCAD assembly solids", "Geometry", [p("M4 7l5-3 5 3-5 3zM4 7v6l5 3 5-3V7M14 10l3-2 4 2-4 2zM14 10v6l3 2 4-2v-6")]);
export const Cable = defineIcon("Cable", "Harness or bond connection", "Electrical", [p("M5 5h4v4H7v4a5 5 0 0 0 10 0V9h-2V5h4M3 3h2v4H3zM19 3h2v4h-2z")]);
export const Network = defineIcon("Network", "Connected electrical topology", "Electrical", [c(5, 6, 2), c(19, 6, 2), c(12, 18, 2), p("M7 7l4 9M17 7l-4 9M7 6h10")]);
export const Radar = defineIcon("Radar", "EMI risk screening", "RF / SI", [p("M12 12l7-3M12 4a8 8 0 1 0 8 8M12 8a4 4 0 1 0 4 4"), c(12, 12, 1)]);
export const RadioTower = defineIcon("RadioTower", "RF radiation source", "RF / SI", [p("M12 5v14M9 21h6M10 19l2-7 2 7M7 8a7 7 0 0 0 0 8M17 8a7 7 0 0 1 0 8M4 5a11 11 0 0 0 0 14M20 5a11 11 0 0 1 0 14")]);
export const SatelliteDish = defineIcon("SatelliteDish", "Far-field radiation pattern", "RF / SI", [p("M5 4a11 11 0 0 0 15 15M5 4v7a8 8 0 0 0 8 8h7M12 12l7-7M15 5h4v4"), c(11, 13, 1)]);
export const ScanLine = defineIcon("ScanLine", "Near-field scan plane", "RF / SI", [p("M4 5h16v14H4zM4 10h16M9 5v14M15 5v14M6 16c3-5 8-5 12 0")]);
export const MapPinPlus = defineIcon("MapPinPlus", "Place a measurement probe", "Results", [p("M12 21s6-6 6-12a6 6 0 1 0-12 0c0 6 6 12 6 12zM12 6v6M9 9h6")]);
export const TableProperties = defineIcon("TableProperties", "Engineering data table", "Results", [r(3, 4, 18, 16, 1), p("M3 9h18M9 9v11M9 14h12"), c(6, 14, 1)]);
export const FileChartColumn = defineIcon("FileChartColumn", "Engineering report", "Results", [p("M6 3h8l4 4v14H6zM14 3v5h4M9 17v-3M12 17v-6M15 17v-4")]);
export const SquareTerminal = defineIcon("SquareTerminal", "Python or solver console", "Application", [r(3, 4, 18, 16, 2), p("M7 9l3 3-3 3M12 16h5")]);
export const BatteryCharging = defineIcon("BatteryCharging", "Power integrity and DC delivery", "Electrical", [r(3, 7, 16, 10, 2), p("M19 10h2v4h-2M8 9l-2 4h4l-2 3M13 10h3M13 14h3")]);
export const Waypoints = defineIcon("Waypoints", "Bulk net routes", "Electrical", [c(5, 5, 2), c(19, 7, 2), c(7, 19, 2), p("M7 5h4a4 4 0 0 1 4 4v3a4 4 0 0 1-4 4H9M17 8l-3 3")]);
export const AudioWaveform = defineIcon("AudioWaveform", "Transient waveform", "Results", [p("M3 12h2l2-7 3 14 3-10 3 6 2-3h3")]);
export const Workflow = defineIcon("Workflow", "Power-tree workflow", "Electrical", [r(3, 3, 6, 5, 1), r(15, 16, 6, 5, 1), r(3, 16, 6, 5, 1), p("M9 5.5h4a4 4 0 0 1 4 4V16M6 8v8")]);
export const Magnet = defineIcon("Magnet", "Magnetic coupling risk", "RF / SI", [p("M5 4h5v8a2 2 0 0 0 4 0V4h5v8a7 7 0 0 1-14 0zM5 8h5M14 8h5")]);
export const Split = defineIcon("Split", "Near-end and far-end crosstalk", "RF / SI", [p("M4 6h5a3 3 0 0 1 3 3v6a3 3 0 0 0 3 3h5M4 18h5a3 3 0 0 0 3-3M17 3l3 3-3 3M17 15l3 3-3 3")]);
export const Binary = defineIcon("Binary", "PAM and digital signaling", "RF / SI", [p("M5 5v6M3 5h4M3 11h4M12 5h4v6h-4zM5 16v3M3 16h4M3 19h4M13 16v3M11 16h4M11 19h4M19 5v6M17 5h4M17 11h4")]);
export const GalleryVertical = defineIcon("GalleryVertical", "Layer visibility gallery", "Geometry", [r(4, 3, 16, 5, 1), r(4, 10, 16, 5, 1), r(4, 17, 16, 4, 1), c(7, 5.5, .7)]);
export const Route = defineIcon("Route", "Selected net domain", "Electrical", [c(5, 5, 2), c(19, 19, 2), p("M7 5h5v5h5v7M9 19H7a2 2 0 0 1-2-2V9")]);
export const ClipboardCheck = defineIcon("ClipboardCheck", "Analysis preflight", "Application", [r(5, 4, 14, 17, 2), p("M9 4V2h6v2M8 13l3 3 5-6")]);
export const FileCog = defineIcon("FileCog", "Prepared solver case", "Application", [p("M5 3h9l5 5v13H5zM14 3v6h5"), c(12, 15, 2.5), p("M12 11v1M12 18v1M8 15h1M15 15h1")]);
export const ServerCog = defineIcon("ServerCog", "Solver runtime manager", "Application", [r(3, 4, 18, 6, 2), r(3, 14, 10, 6, 2), c(7, 7, .8), c(7, 17, .8), c(18, 17, 2.5), p("M18 13v1M18 20v1M14 17h1M21 17h1")]);
export const LayoutDashboard = defineIcon("LayoutDashboard", "Analysis dashboard", "Results", [r(3, 3, 8, 8, 1), r(13, 3, 8, 5, 1), r(13, 10, 8, 11, 1), r(3, 13, 8, 8, 1), p("M15 18l2-4 2 2")]);
export const Flame = defineIcon("Flame", "Heat source", "Thermal", [p("M12 3c1 5-4 5-4 10a4 4 0 0 0 8 0c0-2-1-3-2-4 0 3-4 3-2-6zM12 14c1 1 1 3 0 4")]);
export const Wind = defineIcon("Wind", "Airflow channel", "Thermal", [p("M3 7h11c3 0 3-4 0-4M3 12h15c4 0 4 5 0 5M3 17h8c3 0 3 4 0 4")]);
export const Fan = defineIcon("Fan", "Cooling fan placement", "Thermal", [c(12, 12, 2), c(12, 12, 9), p("M12 10c-1-4 1-6 4-5 3 2 1 5-2 7M14 12c4-1 6 1 5 4-2 3-5 1-7-2M12 14c1 4-1 6-4 5-3-2-1-5 2-7M10 12c-4 1-6-1-5-4 2-3 5-1 7 2")]);
export const CloudSun = defineIcon("CloudSun", "Ambient thermal environment", "Thermal", [c(17, 7, 3), p("M17 2v1M22 7h1M20.5 3.5l.7-.7M5 18h13a3 3 0 0 0 0-6 6 6 0 0 0-11-2 4 4 0 0 0-2 8z")]);
export const ListTree = defineIcon("ListTree", "Scenario hierarchy", "Application", [p("M5 4v15M5 8h5M5 15h5M10 8v4h4"), r(14, 10, 7, 5, 1), r(10, 3, 8, 4, 1), r(10, 17, 8, 4, 1)]);
export const ScanSearch = defineIcon("ScanSearch", "Hover inspection probe", "Results", [p("M4 8V4h4M16 4h4v4M4 16v4h4M20 16v4h-4"), c(11, 11, 4), p("M14 14l4 4")]);
export const Zap = defineIcon("Zap", "Voltage quantity", "Electrical", [p("M13 2 5 13h6l-1 9 9-12h-6z"), p("M4 18h3M17 5h3")]);
export const ArrowRightLeft = defineIcon("ArrowRightLeft", "Current flow quantity", "Electrical", [p("M4 8h14l-3-3M18 8l-3 3M20 16H6l3-3M6 16l3 3"), c(12, 12, 1)]);
export const GitCompareArrows = defineIcon("GitCompareArrows", "Compare result cases", "Results", [p("M7 4v13a3 3 0 0 0 3 3h5M4 7l3-3 3 3M17 20V7a3 3 0 0 0-3-3h-3M20 17l-3 3-3-3")]);
export const Layers2 = defineIcon("Layers2", "Cross-layer relation", "Geometry", [p("M3 8l9-5 9 5-9 5zM5 14l7 4 7-4M12 13v8M9 18l3 3 3-3")]);
export const FileSpreadsheet = defineIcon("FileSpreadsheet", "CSV or tabular export", "Results", [p("M5 3h9l5 5v13H5zM14 3v6h5M8 12h8v6H8zM12 12v6M8 15h8")]);
export const ChartScatter = defineIcon("ChartScatter", "Sampled field results", "Results", [p("M4 3v17h17"), c(8, 15, 1), c(11, 10, 1), c(15, 13, 1), c(18, 7, 1), p("M7 17l4-7 4 3 4-7")]);
export const ChartArea = defineIcon("ChartArea", "Power-integrity result area", "Results", [p("M4 4v16h17M5 17l4-6 4 2 4-7 3 3v8z"), p("M5 17h15")]);
export const Printer = defineIcon("Printer", "Print or PDF report", "Results", [r(6, 3, 12, 6, 1), r(6, 15, 12, 6, 1), p("M6 18H4V9h16v9h-2M16 12h1")]);
export const ChartNoAxesCombined = defineIcon("ChartNoAxesCombined", "Combined analytics", "Results", [p("M4 18l5-6 4 3 7-9M5 8v10M9 6v6M13 9v6M17 4v6"), c(20, 6, 1)]);
export const Settings2 = defineIcon("Settings2", "Application settings", "Application", [p("M4 7h10M18 7h2M4 17h2M10 17h10"), c(16, 7, 2), c(8, 17, 2), p("M4 12h4M12 12h8"), c(10, 12, 2)]);
export const Search = defineIcon("Search", "Find commands and objects", "Application", [c(10, 10, 6), p("M14.5 14.5 21 21M7 10h6M10 7v6")]);
export const X = defineIcon("X", "Close the current surface", "Application", [p("M5 5l14 14M19 5 5 19"), c(12, 12, 10)]);
export const Plus = defineIcon("Plus", "Add an item", "Application", [c(12, 12, 9), p("M12 7v10M7 12h10")]);
export const Save = defineIcon("Save", "Save the current artifact", "Application", [p("M4 3h13l3 3v15H4zM8 3v6h8V3M8 21v-7h8v7"), c(14, 6, .7)]);
export const Play = defineIcon("Play", "Run the selected workflow", "Application", [c(12, 12, 9), p("M10 8l7 4-7 4z"), l(6, 19, 18, 19)]);
export const RefreshCw = defineIcon("RefreshCw", "Refresh a bounded data source", "Application", [p("M19 8a8 8 0 0 0-14-2L3 8M3 4v4h4M5 16a8 8 0 0 0 14 2l2-2M21 20v-4h-4")]);
export const Trash2 = defineIcon("Trash2", "Remove an item", "Application", [p("M5 7h14M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6")]);

export const PowerIntegrityIcon = BatteryCharging;
export const SignalIntegrityIcon = ChartSpline;
export const ThermalAnalysisIcon = ThermometerSun;
export const RFFieldIcon = RadioTower;
export const MCADAssemblyIcon = Boxes;
export const BoardIcon = CircuitBoard;
export const PortIcon = Plug;
export const MeshIcon = Grid3X3;
export const ProbeIcon = Crosshair;
export const MaterialIcon = Layers3;
export const PlotIcon = ChartScatter;
export const TableIcon = TableProperties;
export const ReportIcon = FileChartColumn;
export const PythonIcon = SquareTerminal;

export const workbenchIconInventory: readonly WorkbenchIconMeta[] = inventory;
