// SPDX-License-Identifier: Apache-2.0
// Render only admitted, actually returned Optycal evidence; no synthetic fields.
import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
const bundle = await build({ entryPoints: ['src/optycalReport.ts'], bundle: true, platform: 'node', format: 'esm', write: false });
const { optycalReportHtml } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`);
const input = resolve(process.argv[2] ?? '../examples/optycal/result.json');
const output = resolve(process.argv[3] ?? '../examples/optycal/report.html');
const result = JSON.parse(await readFile(input, 'utf8'));
await mkdir(dirname(output), { recursive: true });
await writeFile(output, optycalReportHtml(result), 'utf8');
console.log(`Wrote actual Optycal report: ${output}`);
