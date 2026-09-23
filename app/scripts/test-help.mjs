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
for (const file of fs.readdirSync(path.join(root, '../docs')).filter(f => f.endsWith('.md'))) {
  const output = render(fs.readFileSync(path.join(root, '../docs', file), 'utf8'));
  assert.ok(output.length > 0, file);
}
for (const file of ['marble-workspace-3d.png', 'marble-layout-layers.png', 'marble-net-names.png', 'marble-report-preview.png', 'workspace-3d.png', 'layout-selection.png', 'report-preview.png', 'external-solver-center.png', 'solver-extension-manager.png', 'solver-manager-selection.png', 'studio-batch-probes.png', 'studio-vcd-timing.png']) {
  const bytes = fs.readFileSync(path.join(root, 'public/help', file));
  // Historical real captures can be JPEG-encoded despite a .png filename.
  // Preserve their original pixels; validate the image encoding, not the suffix.
  const png = bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  const jpeg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
    && bytes.at(-2) === 0xff && bytes.at(-1) === 0xd9;
  assert.ok(bytes.length > 100 && (png || jpeg), `Invalid or truncated help image: ${file}`);
}
console.log(`Help checks passed: ${controls.length} controls, ${reference.commands.length} CLI pages, ${reference.errors.length} diagnostics; search, links, safe Markdown, all reference documents and image assets.`);
