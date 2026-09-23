import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../src/engineeringReport.ts", import.meta.url), "utf8");
const domainSource = readFileSync(new URL("../src/engineeringReportDomain.ts", import.meta.url), "utf8");
const scriptMatch = source.match(/const reportScript = String\.raw`([\s\S]*?)`;\r?\n\r?\nexport function buildEngineeringReport/);
assert.ok(scriptMatch, "the self-contained report runtime must be present");
assert.match(source, /default-src 'none'; script-src 'unsafe-inline';/,
  "offline report CSP must stay self-contained");

function fakeContext(calls) {
  return new Proxy({}, {
    get(_target, property) {
      if (property === "createLinearGradient" || property === "createRadialGradient") return () => ({ addColorStop() {} });
      if (property === "measureText") return () => ({ width: 40 });
      return (...args) => calls.push([property, args]);
    },
    set() { return true; },
  });
}

function element(overrides = {}) {
  const classes = new Set();
  return {
    hidden: false,
    textContent: "",
    innerHTML: "",
    style: {},
    classList: { toggle(name, active) { active ? classes.add(name) : classes.delete(name); }, contains(name) { return classes.has(name); } },
    parentElement: { setAttribute() {} },
    children: [],
    listeners: {},
    addEventListener(type, listener) { this.listeners[type] = listener; },
    click() { this.listeners.click?.(); },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); return child; },
    setAttribute(name, value) { (this.attributes ??= {})[name] = String(value); },
    getAttribute(name) { return this.attributes?.[name] ?? null; },
    getBoundingClientRect() { return { width: 720, height: 420, left: 0, top: 0 }; },
    ...overrides,
  };
}

function runReport({ canvasAvailable }) {
  const boardCalls = [];
  const graphCalls = [];
  const option = element({ textContent: "Absolute voltage", attributes: { "data-unit": "V" } });
  const data = {
    bounds: { minX: 0, minY: 0, maxX: 20, maxY: 10 },
    layers: ["F.Cu"],
    outlineLoops: [[[0, 0], [20, 0], [20, 10], [0, 10]]],
    tracks: [{ s: [1, 2], e: [18, 8], w: 0.35, l: "F.Cu", n: "VDD" }],
    vias: [], pads: [], zones: [], components: [],
    fields: {
      voltage_v: [
        { x_mm: 1, y_mm: 2, layer: "F.Cu", net: "VDD", value: 12 },
        { x_mm: 18, y_mm: 8, layer: "F.Cu", net: "VDD", value: 11.94 },
      ],
      voltage_drop_v: [], current_a: [], current_density_a_mm2: [],
      operating_point_impedance_ohm: [], power_loss_w: [], via_current_density_a_mm2: [],
    },
    timeSeries: [], impedance: [],
  };
  data.datasets = [
    { id: "net-0", fields: data.fields, impedance: [] },
    { id: "net-1", fields: { ...data.fields, voltage_v: data.fields.voltage_v.map(sample => ({ ...sample, value: sample.value + 2 })) }, impedance: [] },
  ];
  const elements = {
    "report-data": element({ textContent: JSON.stringify(data) }),
    "evidence-data": element({ textContent: "{}" }),
    "report-runtime-diagnostic": element({ hidden: true }),
    "board-canvas": element({ getContext: () => canvasAvailable ? fakeContext(boardCalls) : null }),
    "result-chart": element({ getContext: () => fakeContext(graphCalls) }),
    "viewport-metric": element({ value: "voltage_v", selectedIndex: 0, options: [option] }),
    "graph-series": element({ value: "voltage_v", selectedIndex: 0, options: [option] }),
    "plotly-metric": element({ value: "voltage_v", selectedIndex: 0, options: [option] }),
    "plotly-field": element({ innerHTML: '<div class="empty-result">lightweight viewer active</div>' }),
    "graph-tooltip": element(), "viewport-tooltip": element(), "viewport-colorbar": element(),
    "color-min": element(), "color-max": element(), "color-unit": element(), "interaction-hint": element(),
    "print-report": element(), "download-evidence": element(),
  };
  const tabA = element({ attributes: { "data-net-tab": "net-0" } });
  const tabB = element({ attributes: { "data-net-tab": "net-1" } });
  const panelA = element({ attributes: { "data-net-panel": "net-0" } });
  const panelB = element({ attributes: { "data-net-panel": "net-1" } });
  const document = {
    body: { firstChild: null, insertBefore() {}, appendChild() {} },
    getElementById(id) { return elements[id] ?? null; },
    querySelectorAll(selector) { return selector === "[data-net-tab]" ? [tabA, tabB] : selector === "[data-net-panel]" ? [panelA, panelB] : []; },
    createElement() { return element(); },
  };
  const reportConsole = { error() {}, warn() {}, log() {} };
  const window = { addEventListener() {}, console: reportConsole, devicePixelRatio: 1, print() {}, focus() {} };
  vm.runInNewContext(scriptMatch[1], {
    window, document, console: reportConsole, JSON, Math, Number, Object, Array, Error,
    Blob: class {}, URL: { createObjectURL() { return "blob:test"; }, revokeObjectURL() {} }, setTimeout,
  }, { filename: "minimal-engineering-report-runtime.js" });
  return { boardCalls, graphCalls, elements, tabA, tabB, panelA, panelB };
}

const healthy = runReport({ canvasAvailable: true });
assert.ok(healthy.boardCalls.some(([name]) => name === "fillRect"), "board canvas must draw independently");
assert.ok(healthy.graphCalls.some(([name]) => name === "stroke"), "result graph must draw independently");
const firstBoardVertex = healthy.boardCalls.find(([name]) => name === "moveTo")?.[1];
assert.ok(firstBoardVertex, "board outline must be projected");
assert.ok(firstBoardVertex[0] < 100 && firstBoardVertex[1] < 100,
  "2D report projection must preserve the layout's top-left origin instead of vertically mirroring it");
assert.equal(healthy.elements["report-runtime-diagnostic"].hidden, true,
  "the lightweight report runtime must initialize without a diagnostic");
assert.equal(healthy.panelA.hidden, false, "the first net panel must be visible initially");
assert.equal(healthy.panelB.hidden, true, "inactive net panels must be hidden on screen");
const boardCallsBeforeNetChange = healthy.boardCalls.length;
const graphCallsBeforeNetChange = healthy.graphCalls.length;
healthy.tabB.click();
assert.equal(healthy.panelA.hidden, true, "selecting another net must hide the previous panel");
assert.equal(healthy.panelB.hidden, false, "selecting another net must show its panel");
assert.ok(healthy.boardCalls.length > boardCallsBeforeNetChange, "selecting a net must redraw the board field preview");
assert.ok(healthy.graphCalls.length > graphCallsBeforeNetChange, "selecting a net must redraw the result graph");

const missingCanvas = runReport({ canvasAvailable: false });
assert.match(missingCanvas.elements["report-runtime-diagnostic"].textContent, /Board canvas/i,
  "a missing canvas context must identify the failing surface");

assert.doesNotMatch(source, /plotly\.js-dist-min|embeddedPlotly|window\.Plotly/,
  "reports must not carry the multi-megabyte duplicate Plotly runtime");
assert.match(source, /var worldY=-dy/,
  "3D report projection must use the live viewport's board-Y to world-Y convention");
assert.match(source, /const REPORT_TABLE_ROW_LIMIT = 500/,
  "large report tables must have an explicit responsive-display bound");
assert.match(source, /<section id="thermal-results"><h2>Thermal Analysis Result<\/h2>/,
  "thermal reports must expose a domain-specific result section");
assert.match(source, /<section id="si-results"><h2>Signal-Integrity Channel Result<\/h2>/,
  "SI reports must expose a domain-specific result section");
assert.match(source, /<section id="pi-results"><h2>Power-Integrity Result<\/h2>/,
  "PI reports must expose a domain-specific result section");
assert.match(source, /includeEmi \? `\$\{emiReportHtml\}\$\{emiFieldReportHtml\}` : ""/,
  "EMI material must be gated to an explicitly EMI-classified report");
assert.match(source, /\.net-panel,\.net-panel\[hidden\]\{display:block!important;break-before:page/,
  "print and PDF output must restore every net panel in sequential pages");
assert.match(source, /data-net-tab=/, "interactive HTML reports must expose per-net tabs");
assert.doesNotMatch(source, /function contourGrid|Math\.(?:min|max)\.apply/,
  "the offline runtime must neither infer a rectangular contour grid nor spread large arrays into extrema calls");
assert.match(source, /sample\.vertices_mm\|\|\[\]/,
  "contours must be built only from explicit solver-face vertices");
assert.match(source, /samples\.length&&fieldDisplay!==['"]raw['"]\)\{drawContour/,
  "both 2D smooth and 3D contour modes must render explicit solver faces");
assert.match(source, /const viewportOptions = `\$\{stats\.map/,
  "the first returned quantity must be the default preview instead of empty geometry");
assert.match(source, /value:triangle\.sample\.value/,
  "contour hover must report the authoritative source sample value");
assert.match(source, /value === null \|\| value === undefined \|\| value === ""/,
  "missing result values must remain Not returned instead of coercing to zero");
assert.match(domainSource, /return "emi"/,
  "EMI must be a distinct report discipline rather than falling through to PI");
assert.match(source, /Do not add per-layer flips/,
  "the report must document its single coordinate-transform policy");

console.log("engineering report runtime fallback assertions passed");
