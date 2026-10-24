// SPDX-License-Identifier: Apache-2.0
import { reportPlotRuntime } from "./reportPlotInteraction";
export type ReportPresentation = {
  title: string;
  projectName: string;
  reportId: string;
  generatedAt: string;
  opening: string;
  closing: string;
};

const escape = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[c]!);
const cssText = (value: string) => value.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/[\r\n]/g, " ")
  .replace(/</g, "\\3c ").replace(/>/g, "\\3e ").replace(/&/g, "\\26 ");
const text = (markup: string) => markup.replace(/<[^>]*>/g, "").trim();

// Shared by offline exports. No remote assets or runtime framework is needed.
const presentationCss = `
html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:#edf1f5;color:#213342;font:14px/1.6 Arial,Helvetica,sans-serif}
*{box-sizing:border-box}a{color:#145b80}button,select,input{font:inherit}
.report-plot-tools{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:10px 0;font-size:11px;color:#587083}.report-plot-tools button,.report-plot-tools select{height:28px;padding:3px 8px;border:1px solid #aac0ce;border-radius:4px;background:#fff;color:#234e68}.report-plot-tools label{white-space:nowrap}svg[data-spike-plot]{overflow:hidden;outline-offset:2px}svg[data-spike-plot]:focus-visible{outline:2px solid #1776a4}svg[data-spike-plot] [data-plot-traces] polyline{vector-effect:non-scaling-stroke}@media print{.report-plot-tools{display:none!important}}
.report-header{background:#142c3a;border-bottom:3px solid #dfaa48}
.header-inner{width:min(1540px,calc(100% - 48px));min-height:110px;padding:20px 0}
.report-header h1{font-size:27px;line-height:1.2;letter-spacing:-.4px}
.report-header p{overflow-wrap:anywhere;max-width:850px;font-size:12px}
.identity{min-width:0}.identity code{overflow-wrap:anywhere}
.report-layout{display:grid;grid-template-columns:238px minmax(0,1fr);gap:24px;max-width:1540px;margin:24px auto;padding:0 24px;align-items:start}
.report-sidebar{position:sticky;top:18px;min-width:0}
.report-navigation{background:#fff;border:1px solid #d4dfe7;border-radius:8px;box-shadow:0 2px 7px #1835470a}
.report-navigation>summary{padding:14px 16px;background:#fff;border:0;border-radius:8px;font-size:13px;color:#223d50}
.report-navigation nav{max-height:calc(100vh - 100px);overflow:auto;padding:0 8px 12px}
.report-navigation a{display:flex;gap:9px;align-items:baseline;text-decoration:none;color:#465b6b;line-height:1.35;padding:9px 10px;border-left:3px solid transparent;border-radius:3px;font-size:12px;overflow-wrap:anywhere}
.report-navigation a:hover,.report-navigation a:focus-visible{background:#eef5f9;color:#105b83;outline:2px solid #8baebf;outline-offset:-2px}
.report-navigation a[aria-current=location]{background:#eaf3f8;color:#0c567e;border-left-color:#1776a4;font-weight:bold}
.report-navigation .nav-index{color:#7a8e9c;font-size:10px;min-width:16px}
.report-navigation .nav-net{margin-left:15px;font-size:11px;padding:7px 9px;border-left-color:#e0e8ed}
.report-main{min-width:0;width:100%;margin:0;padding:32px 38px;background:#fff;border:1px solid #d4dfe7;border-radius:8px;box-shadow:0 2px 10px #1b35470a}
.report-main>h1{display:none}.report-main>button{margin-bottom:18px}
.report-main section{content-visibility:visible;contain-intrinsic-size:none;margin:0 0 34px;scroll-margin-top:24px}
.report-main h2{font-size:21px;line-height:1.35;letter-spacing:-.2px;margin:0 0 16px;padding:0 0 10px;border-bottom:2px solid #dce7ee;color:#18394f}
.report-main h3{font-size:15px;line-height:1.4;margin:22px 0 10px;color:#29485d}
.report-main p{margin:10px 0 16px;max-width:100%;font-size:13px;line-height:1.65}
.report-main .section-intro,.report-caption{color:#5b7181;line-height:1.6;font-size:12px;max-width:none}
.report-opening{padding:0 0 8px}.report-opening p{font-size:14px;max-width:850px}
.status-banner{border-radius:5px;gap:14px;padding:13px 16px;font-size:12px;line-height:1.6;margin-bottom:28px;flex-wrap:wrap}
.summary-grid{gap:20px}.metrics{background:#f6f9fb;border:1px solid #dbe5eb;border-radius:5px;overflow:hidden}
.metric{padding:18px 15px;min-width:0}.metric span{font-size:10px;line-height:1.5;letter-spacing:.3px}.metric strong{font-size:23px;line-height:1.25;overflow-wrap:anywhere}
.summary-table,.data-table{width:100%;border-collapse:collapse;font-size:11px;line-height:1.5}
.summary-table th,.summary-table td,.data-table th,.data-table td{border:1px solid #d8e2e9;padding:9px 10px;vertical-align:top;overflow-wrap:anywhere}
.data-table th,.summary-table th{background:#edf3f7;color:#345064;font-size:10px;letter-spacing:.2px}
.data-table tbody tr:nth-child(even){background:#f8fafc}.data-table tbody tr:hover{background:#edf6fb}
.report-table-wrap{max-width:100%;overflow:auto;margin:12px 0 18px}.report-table-wrap:focus-visible{outline:2px solid #558ea9}
.report-table-wrap .data-table{min-width:650px}.report-table-wrap .summary-table{min-width:440px}
.analytics-note{border-color:#4386a8;background:#f0f7fb;padding:14px 18px;border-radius:0 5px 5px 0}.analytics-note p{margin-bottom:0}
.object-id{max-width:none;white-space:normal;overflow-wrap:anywhere;font-size:10px;line-height:1.5}
.net-tabs{flex-wrap:wrap;overflow:visible;gap:5px;margin:14px 0}.net-tabs button{border-radius:4px;padding:7px 12px;font-size:12px}
.net-panel{padding:20px;border-radius:5px;border-color:#d8e3ea;background:#fff;margin:0 0 20px;scroll-margin-top:24px}
.net-panel>header{flex-wrap:wrap}.net-panel>header h3{font-size:20px;margin:4px 0}.net-panel>header code{font-size:10px;color:#778c9b}
.net-kpis{gap:8px}.net-kpis>div{padding:13px;background:#f1f6f9;border-top:2px solid #67a5c1}.net-kpis b{font-size:17px;overflow-wrap:anywhere}
.net-plots{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.net-plot{border-radius:4px;padding:12px}.net-plot figcaption{gap:10px;flex-wrap:wrap;font-size:12px}
.net-plot svg{height:155px}.net-plot small{display:block;line-height:1.5}.net-plots:has(>.net-plot:only-child){grid-template-columns:1fr}
.visual-shell,.graph-shell{border-radius:5px;overflow:hidden}.visual-shell{background:#101a20}
.view-toolbar{min-height:42px;padding:6px 8px;flex-wrap:wrap;gap:6px}.view-toolbar button{padding:5px 9px;font-size:11px;min-height:30px;border-radius:3px}.view-toolbar select{min-width:0;max-width:290px;height:30px;font-size:11px}
.view-toolbar small{font-size:10px}.canvas-wrap{height:clamp(280px,38vw,430px)}
.graph-tools{flex-wrap:wrap;font-size:12px}.graph-tools select{min-width:0;max-width:100%;font-size:12px}.graph-tools span{font-size:11px;color:#617787}.graph-wrap{height:280px}
.report-static-figure{margin:14px 0 20px;padding:15px;border:1px solid #d5e1e8;background:#f8fafc;border-radius:5px;break-inside:avoid}
.report-static-figure svg{display:block;width:100%;max-height:360px}.report-static-figure figcaption{font-size:11px;color:#587083;line-height:1.5;margin-top:8px}
.visual-shell[data-render-ready=true]+.report-static-figure,.graph-shell[data-render-ready=true]+.report-static-figure{display:none}
.empty-result{background:#f6f9fb;border:1px dashed #c6d6e0;padding:20px;border-radius:5px;color:#597080;font-size:12px}
.trace-grid{gap:16px}.trace-box{border-radius:5px}.trace-box dl{grid-template-columns:140px minmax(0,1fr);font-size:11px}
.setup-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.setup-grid>div{min-width:0}.setup-grid h3{margin-top:0}
.report-main pre{background:#f3f6f9;color:#344d60;border:1px solid #d9e3e9;font:10px/1.65 Consolas,monospace;border-radius:3px}
.report-main details{border-color:#d5e0e8;border-radius:4px}.report-main summary{font-size:12px;padding:10px 12px;background:#f3f7fa}
.print-cover,.print-contents{display:none}.report-closing{padding:22px;background:#f3f7fa;border:1px solid #d3e1ea;border-radius:5px}
.report-footer{border-top:1px solid #cad8e1;background:#e5ecf1;color:#5d7483}.footer-inner{width:min(1540px,calc(100% - 48px));min-height:58px;font-size:11px}.footer-inner b{color:#304e62}
@media(max-width:1100px){.report-layout{grid-template-columns:205px minmax(0,1fr);gap:16px;padding:0 16px}.report-main{padding:26px 24px}.summary-grid,.trace-grid{grid-template-columns:1fr}.header-inner{grid-template-columns:1fr}.identity{text-align:left}.header-actions{justify-content:flex-start}.metric strong{font-size:21px}}
@media(max-width:760px){.report-layout{display:block;margin:14px auto;padding:0 10px}.report-sidebar{position:static;margin-bottom:14px}.report-navigation nav{max-height:220px}.report-main{padding:22px 16px}.header-inner{width:100%;padding:18px}.report-header h1{font-size:23px}.brand-line{align-items:flex-start}.net-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.setup-grid,.net-plots{grid-template-columns:1fr}.canvas-wrap{height:300px}.trace-box dl{grid-template-columns:110px minmax(0,1fr)}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@page{size:A4 landscape;margin:17mm 13mm 18mm;@bottom-right{content:"Page " counter(page) " of " counter(pages);font:8pt Arial;color:#597080}}
@media print{
 html{scroll-behavior:auto}body{background:#fff;color:#172e3e;font:9pt/1.45 Arial,sans-serif}
 .report-header,.report-sidebar,.report-footer,.report-nav,.header-actions,.view-toolbar,.net-tabs,.graph-tools,.canvas-wrap,.graph-wrap,.plotly-shell,.visual-shell,.graph-shell,.report-main>button{display:none!important}
 .report-layout{display:block;margin:0;padding:0;max-width:none}.report-main{border:0;border-radius:0;box-shadow:none;width:100%;padding:0;counter-reset:report-section}
 .print-cover{display:flex;flex-direction:column;justify-content:center;min-height:160mm;break-after:page;padding:12mm 16mm;border-top:5mm solid #173d55}
 .print-cover .cover-brand{font-size:12pt;color:#38667f;letter-spacing:1.5px;font-weight:bold;margin-bottom:12mm}.print-cover h1{font-size:30pt;line-height:1.15;max-width:210mm;color:#183e56;margin:0 0 8mm}.print-cover .cover-project{font-size:17pt;overflow-wrap:anywhere}.print-cover dl{display:grid;grid-template-columns:35mm 1fr;gap:3mm;margin-top:14mm;font-size:10pt}.print-cover dt{color:#6b8190}.print-cover dd{margin:0;overflow-wrap:anywhere}.cover-note{margin-top:12mm;font-size:9pt;color:#536f80}
 .print-contents{display:block;break-after:page;padding:4mm 0}.print-contents h2{font-size:23pt}.print-contents ol{list-style:none;padding:0;columns:2;column-gap:14mm}.print-contents li{break-inside:avoid;padding:3mm 0;border-bottom:1px solid #e1e9ef;font-size:10pt}.print-contents a{text-decoration:none;color:#234e68}.print-contents .toc-net{display:block;font-size:9pt;margin:2mm 0 0 8mm}.print-contents .nav-index{display:inline-block;min-width:8mm;color:#76909f}
 .report-main section{content-visibility:visible;contain-intrinsic-size:none;break-inside:auto;margin-bottom:7mm}.report-main section>h2{counter-increment:report-section}.report-main section>h2::before{content:counter(report-section) ". ";color:#6f8796}
 .report-main h2{font-size:15pt;padding-bottom:2mm;margin-bottom:4mm;break-after:avoid}.report-main h3{font-size:10pt;break-after:avoid;margin-top:5mm}.report-main p{font-size:9pt;line-height:1.5;orphans:3;widows:3}
 .report-table-wrap{overflow:visible;margin:3mm 0 5mm}.report-table-compact{break-inside:avoid}.report-table-wrap table{min-width:0!important;width:100%;table-layout:fixed}.summary-table,.data-table{display:table!important;overflow:visible;font-size:8pt;line-height:1.35}.summary-table th,.summary-table td,.data-table th,.data-table td{padding:2mm 1.5mm;font-size:7.5pt;word-break:normal;overflow-wrap:anywhere}.data-table thead{display:table-header-group}.data-table tr,.summary-table tr{break-inside:avoid}
 .summary-grid{grid-template-columns:1.1fr .9fr;gap:6mm}.metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.metric{padding:4mm}.metric strong{font-size:15pt}.metric span{font-size:7pt}
 .net-panel,.net-panel[hidden]{display:block!important;break-before:page;break-inside:auto;border:0;padding:0;margin-bottom:7mm}.net-panel:first-child{break-before:auto}.net-panel>header{break-after:avoid}.net-kpis{grid-template-columns:repeat(4,minmax(0,1fr));margin:4mm 0}.net-kpis b{font-size:11pt}.net-plots{grid-template-columns:repeat(3,minmax(0,1fr));gap:3mm}.net-plot{break-inside:avoid;padding:3mm}.net-plot svg{height:35mm}.net-plots:has(>.net-plot:only-child) .net-plot svg{height:50mm}
 .report-static-figure,.visual-shell[data-render-ready=true]+.report-static-figure,.graph-shell[data-render-ready=true]+.report-static-figure{display:block!important;background:#fff;border:1px solid #d8e3eb;padding:4mm}.report-static-figure svg{max-height:90mm}.report-static-figure figcaption{font-size:8pt;margin-top:3mm}
 .report-caption,.object-id{font-size:8pt;max-width:none}.analytics-note,.report-closing{padding:4mm;break-inside:avoid}.trace-grid{grid-template-columns:1fr 1fr}.setup-grid{grid-template-columns:1fr 1fr}.report-main pre{max-height:none;overflow:visible;font-size:7pt;line-height:1.45}
 #study-setup,#visualization,#graphs,#definition{break-before:page}#pi-results,#summary,#validity{break-inside:avoid}.page-break{break-before:page}.report-closing{break-before:page}.print-header{position:fixed;top:-12mm;font-size:7pt;gap:10mm;line-height:1.2}.print-header b{max-width:210mm;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.fixed-print-footer{position:fixed;bottom:-12mm;font-size:7pt;line-height:1.3;gap:10mm}.fixed-print-footer span{max-width:135mm;overflow-wrap:anywhere}.viewport-tooltip,.graph-tooltip{display:none}
}
`;

/** Wraps controlled report markup with screen navigation and printable front matter. */
export function formatReportDocument(document: string, metadata: ReportPresentation): string {
  let output = document.replace(/<nav class="report-nav">[\s\S]*?<\/nav>/, "");
  if (!/<header class="report-header"/.test(output)) output = output.replace(/<body([^>]*)>/,
    `<body$1><header class="report-header"><div class="header-inner"><div><div class="eyebrow">SPIKE / ENGINEERING REPORT</div><h1>${escape(metadata.title)}</h1><p>${escape(metadata.projectName)}</p></div><div class="identity"><code>${escape(metadata.reportId)}</code><span>Generated ${escape(metadata.generatedAt)}</span></div></div></header>`);
  output = output.replace(/<table\b([\s\S]*?)<\/table>/g,
    table => `<div class="report-table-wrap${(table.match(/<tr\b/g)?.length ?? 0) <= 12 ? " report-table-compact" : ""}" role="region" tabindex="0" aria-label="Report data table">${table}</div>`);
  if (!/<main\b/.test(output)) output = output.replace(/<body([^>]*)>([\s\S]*?)<\/body>/,
    (_match, attributes: string, body: string) => `<body${attributes}><main class="report-main">${body}</main></body>`);
  const opening = `<section id="report-opening" class="report-opening"><h2>Purpose and scope</h2><p>${escape(metadata.opening)}</p></section>`;
  const closing = `<section id="report-closing" class="report-closing"><h2>Conclusions and next steps</h2><p>${escape(metadata.closing)}</p><p>Review the setup, returned result status, model limitations and warnings before using this report to make an engineering decision. Retain the source project and full result artifacts with this report.</p></section>`;
  output = output.replace(/(<main\b[^>]*>)/, `$1${opening}`).replace(/<\/main>/, `${closing}</main>`);
  let sequence = 0;
  output = output.replace(/<section\b([^>]*)>\s*<h2>([\s\S]*?)<\/h2>/g, (_match, attributes: string, heading: string) => {
    let id = attributes.match(/\bid="([^"]+)"/)?.[1];
    if (!id) { id = `report-section-${++sequence}`; attributes += ` id="${id}"`; }
    return `<section${attributes}><h2>${heading}</h2>`;
  });
  const sections = [...output.matchAll(/<section\b[^>]*\bid="([^"]+)"[^>]*>\s*<h2>([\s\S]*?)<\/h2>/g)]
    .map((match, index) => ({ id: match[1], label: text(match[2]), index: index + 1 }));
  const nets = [...output.matchAll(/<article\b[^>]*\bid="(net-panel-\d+)"[^>]*data-net-panel="([^"]+)"[^>]*>[\s\S]*?<h3>([\s\S]*?)<\/h3>/g)]
    .map(match => ({ id: match[1], key: match[2], label: text(match[3]) }));
  const links = (toc: boolean) => sections.map(section => {
    const link = `<a href="#${escape(section.id)}"><span class="nav-index">${section.index.toString().padStart(2, "0")}</span><span>${section.label}</span></a>`;
    const netLinks = section.id === "net-review" ? nets.map(net => `<a class="${toc ? "toc-net" : "nav-net"}" href="#${escape(net.id)}" data-nav-net="${escape(net.key)}">${net.label}</a>`).join("") : "";
    return toc ? `<li>${link}${netLinks}</li>` : `${link}${netLinks}`;
  }).join("");
  const sidebar = `<aside class="report-sidebar"><details class="report-navigation" open><summary>Report contents</summary><nav data-report-nav aria-label="Report sections">${links(false)}</nav></details></aside>`;
  const cover = `<div class="print-cover"><div class="cover-brand">SPIKE / ENGINEERING REPORT</div><h1>${escape(metadata.title)}</h1><div class="cover-project">${escape(metadata.projectName)}</div><dl><dt>Report reference</dt><dd>${escape(metadata.reportId)}</dd><dt>Generated</dt><dd>${escape(metadata.generatedAt)}</dd><dt>Document type</dt><dd>Engineering setup, results and review record</dd></dl><div class="cover-note">${escape(metadata.opening)}<br>Qualification and numerical validity remain as stated in the result and limitations.</div></div>`;
  const contents = `<div class="print-contents"><h2>Table of contents</h2><ol>${links(true)}</ol><p>Sections and analyzed nets are linked. All nets are included sequentially in print/PDF output.</p></div>`;
  output = output.replace(/(<main\b[^>]*>)/, `<div class="report-layout">${sidebar}$1${cover}${contents}`).replace(/<\/main>/, "</main></div>");
  output = output.replace(/<\/head>/, `<style>${presentationCss}
@page{@top-left{content:'SPIKE | ${cssText(metadata.title)}';font:7.5pt Arial;color:#426278;vertical-align:bottom;padding-bottom:3mm;width:70%}@top-right{content:'${cssText(metadata.reportId)}';font:7pt Arial;color:#617e90;vertical-align:bottom;padding-bottom:3mm;width:25%}@bottom-left{content:'${cssText(metadata.projectName)}';font:7pt Arial;color:#617e90;width:70%}@bottom-right{content:'Page ' counter(page) ' of ' counter(pages);font:7pt Arial;color:#617e90}}
@page:first{@top-left{content:none}@top-right{content:none}@bottom-left{content:none}@bottom-right{content:none}}
@media print{.print-header,.fixed-print-footer{display:none!important}}
</style></head>`);
  if (!/class="print-header"/.test(output)) output = output.replace(/<body([^>]*)>/,
    `<body$1><div class="print-header"><b>${escape(metadata.title)} | ${escape(metadata.projectName)}</b><span>${escape(metadata.reportId)}</span></div>`);
  if (!/class="fixed-print-footer"/.test(output)) output = output.replace(/<\/body>/,
    `<div class="fixed-print-footer" style="display:none"><span>SPIKE | ${escape(metadata.projectName)}</span><span>${escape(metadata.reportId)} | ${escape(metadata.generatedAt)}</span></div></body>`);
  return output.replace(/<\/body>/, `<script>${reportPlotRuntime}</script></body>`);
}
