import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { searchHelp, resolveHelpLink, helpSlug } from '../src/helpModel.ts';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const helpSource = fs.readFileSync(path.join(root, 'src/HelpCenter.tsx'), 'utf8');
assert.ok(!helpSource.includes('../../docs/*.md'), 'Help must use a curated public document list');
for (const privateName of ['OPEN_SOURCE_RELEASE_PLAN', 'BUSINESS_PLAN', 'DEPLOYMENT_STRATEGY', 'STABILIZATION_RELEASE_PLAN', 'PUBLIC_RELEASE_READINESS']) {
  assert.ok(!helpSource.includes(privateName), `Internal document ${privateName} must not ship in Help`);
}
const reference = JSON.parse(fs.readFileSync(path.join(root, 'src/helpReference.generated.json'), 'utf8'));
const controls = JSON.parse(fs.readFileSync(path.join(root, 'src/helpControls.generated.json'), 'utf8'));
assert.equal(new Set(reference.errors.map(e => e.code)).size, reference.errors.length);
assert.equal(new Set(reference.commands.map(c => c.command)).size, reference.commands.length);
assert.equal(new Set(controls.map(c => c.id)).size, controls.length);
for (const entry of reference.errors) {
  assert.match(entry.code, /^SPIKE-(FE|BE)-[A-Z]+-[IWPECS]-\d{4}$/);
  assert.ok(entry.title && entry.action && entry.message);
}
for (const command of reference.commands) assert.ok(command.usage.includes('usage:'));
assert.ok(reference.commands.every(command => command.command === 'spike' || command.command.startsWith('spike ')), 'Bundled help must contain only SPIKE CLI pages');
for (const name of ['SpiceWorkbench.tsx', 'SParameterWorkbench.tsx', 'SiWorkflowWorkbench.tsx', 'SiProtocolSuiteWorkbench.tsx', 'EmiWorkbench.tsx', 'ThermalAssemblyEditor.tsx', 'TopologyEditor.tsx', 'App.tsx']) assert.ok(controls.some(c => c.file === name), `Missing ${name}`);
const hits = [{ title: 'Solver', text: 'restart the worker after a timeout' }, { title: 'Worker timeout', text: 'Preserve diagnostics' }];
assert.equal(searchHelp(hits, 'worker timeout')[0].title, 'Worker timeout');
assert.equal(searchHelp(hits, 'restart worker').length, 1);
assert.equal(searchHelp(hits, 'not-present').length, 0);
assert.equal(searchHelp(hits, '   ').length, 2);
assert.deepEqual(resolveHelpLink('../TROUBLESHOOTING.md#mesh', 'docs/CLI.md'), { id: 'doc:TROUBLESHOOTING.md', anchor: 'mesh' });
assert.deepEqual(resolveHelpLink('#mesh', 'docs/CLI.md'), { id: 'doc:docs/CLI.md', anchor: 'mesh' });
assert.equal(resolveHelpLink('javascript:alert(1)', 'docs/CLI.md'), null);
assert.equal(resolveHelpLink('//external.invalid', 'docs/CLI.md'), null);
assert.equal(helpSlug('PI: DC drop'), 'pi-dc-drop');

// Exercise the actual Markdown component, including adversarial link/HTML input.
const compiled = ts.transpileModule(fs.readFileSync(path.join(root, 'src/HelpMarkdown.tsx'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;
const module = { exports: {} };
const require = createRequire(import.meta.url);
new Function('require', 'module', 'exports', compiled)(name => name === './helpModel' ? { helpSlug, resolveHelpLink } : require(name), module, module.exports);
const Markdown = module.exports.default;
const render = text => renderToStaticMarkup(React.createElement(Markdown, { text, source: 'docs/CLI.md', navigate() {}, hasTopic: id => id === 'doc:TROUBLESHOOTING.md' }));
const rendered = render('# Heading\n\n| Name | Value |\n| --- | --- |\n| A | 1 |\n\n1. First\n   continued\n2. Next\n\n```text\n<unsafe>\n```\n\n[Recovery](../TROUBLESHOOTING.md)\n\n<script>alert(1)</script>\n\n[bad](javascript:alert)');
assert.match(rendered, /<table>/);
assert.match(rendered, /First continued/);
assert.match(rendered, /#help\//);
assert.ok(!rendered.includes('<script>'));
assert.ok(!rendered.includes('href="javascript:'));
assert.match(rendered, /&lt;unsafe&gt;/);
assert.ok(!render('<!-- SPDX-License-Identifier: Apache-2.0 -->\n\n# Guide').includes('SPDX'));
// Gallery documents must show their shipped figures offline, without admitting
// remote image requests or arbitrary local paths from Markdown.
const galleryAssets = [
  'analytics/pi-dielectric-admittance.png', 'analytics/si-rlgc-line-fields.png',
  'analytics/em-huygens-far-field.png', 'analytics/thermal-two-solid-conduction.png',
  'analytics/hybrid-electrothermal-convergence.png', 'analytics/cfd-native-cavity.png',
  'analytics/cht-laminar-channel.png', 'analytics/multiboard-coupled-networks.png',
  'ui-current/clean-viewport.jpg', 'ui-current/universal-search.jpg', 'ui-current/navigation-map.svg',
];
for (const asset of galleryAssets) {
  assert.ok(fs.statSync(path.join(root, 'public/help', asset)).size > 100, asset);
  const image = render(`![Example](../app/public/help/${asset})`);
  assert.ok(image.includes(`src="/help/${asset}"`), `Offline figure missing: ${asset}`);
}
assert.ok(!render('![Remote](https://example.invalid/analytics/cfd-native-cavity.png)').includes('<img'));
assert.ok(!render('![Unknown](../app/public/help/analytics/not-shipped.png)').includes('<img'));
for (const doc of ['UI_QUICKSTART.md', 'UI_NAVIGATION.md', 'ANALYSIS_GALLERY.md']) {
  assert.ok(helpSource.includes(`../../docs/${doc}`), `${doc} must ship offline`);
}
for (const file of fs.readdirSync(path.join(root, '../docs')).filter(f => f.endsWith('.md'))) {
  const output = render(fs.readFileSync(path.join(root, '../docs', file), 'utf8'));
  assert.ok(output.length > 0, file);
}
assert.ok(!fs.readdirSync(path.join(root, 'public/help')).some(file => file.startsWith('studio-')), 'Separate SPIKES Studio images must not ship in SPIKE Help');
for (const file of ['marble-workspace-3d.png', 'marble-layout-layers.png', 'marble-net-names.png', 'marble-report-preview.png', 'workspace-3d.png', 'layout-selection.png', 'report-preview.png', 'external-solver-center.png', 'solver-extension-manager.png', 'solver-manager-selection.png']) {
  const bytes = fs.readFileSync(path.join(root, 'public/help', file));
  // Historical real captures can be JPEG-encoded despite a .png filename.
  // Preserve their original pixels; validate the image encoding, not the suffix.
  const png = bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  const jpeg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
    && bytes.at(-2) === 0xff && bytes.at(-1) === 0xd9;
  assert.ok(bytes.length > 100 && (png || jpeg), `Invalid or truncated help image: ${file}`);
}
console.log(`Help checks passed: ${controls.length} controls, ${reference.commands.length} CLI pages, ${reference.errors.length} diagnostics; search, links, safe Markdown, all reference documents and image assets.`);

// Authored picture workflows and coverage must remain linked and source-faithful.
await import("./test-help-workflows.mjs");
