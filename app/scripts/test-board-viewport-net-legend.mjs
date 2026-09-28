// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const compile = source => ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022,
} }).outputText;
const load = async source => import(`data:text/javascript;base64,${Buffer.from(compile(source)).toString('base64')}`);
const source = await readFile(new URL('../src/BoardViewport.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('BoardViewport.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const helper = ast.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === 'board3DNetLegend');
assert.ok(helper, 'the 3D viewport must expose a bounded board-net selector');
const copper = await load(await readFile(new URL('../src/copperLayerSelection.ts', import.meta.url), 'utf8'));
const select = new Function('resolveBoardCopperLayers', `${compile(helper.getText(ast))}; return board3DNetLegend;`)(copper.resolveBoardCopperLayers);

const synthetic = {
  layers: ['F.Cu', 'B.Cu'],
  pads: [
    { id: 'ant-pad', ref: 'C1', name: '1', net: '/cpu/ANT', layers: ['F.Cu'] },
    { id: 'ground-pad', ref: 'C1', name: '2', net: 'GND', layers: ['B.Cu'] },
    { id: 'no-net-pad', ref: 'J1', name: '1', layers: ['F.Cu'] },
  ],
  tracks: [{ id: 'supply-track', net: '+3V3', layer: 'F.Cu' }],
  drawings: [{ id: 'antenna-art', layer: 'F.Cu', filled: true }],
};
assert.deepEqual(select(synthetic, {}, null).map(row => row.net), ['/cpu/ANT', 'GND', '+3V3']);
assert.ok(select(synthetic, {}, null).every(row => row.id !== 'antenna-art' && row.id !== 'no-net-pad'));
assert.deepEqual(select(synthetic, { 'F.Cu': false }, null).map(row => row.net), ['GND']);
assert.deepEqual(select(synthetic, {}, 'GND').map(row => row.net), ['GND']);
assert.deepEqual(select(synthetic, {}, null, 2).map(row => row.net), ['/cpu/ANT', 'GND']);

const numeric = await readFile(new URL('../src/numericRange.ts', import.meta.url), 'utf8');
const parser = (await readFile(new URL('../src/boardParser.ts', import.meta.url), 'utf8')).replace('import { numericExtent } from "./numericRange";', '');
const { parseKicadBoard } = await load(`${numeric}\n${parser}`);
const board = parseKicadBoard(await readFile(new URL('../../examples/esp32/source/iot-esp-eth-ind.kicad_pcb', import.meta.url), 'utf8'));
const rows = select(board, {}, null);
assert.ok(rows.length > 0 && rows.length <= 8);
assert.equal(new Set(rows.map(row => row.net)).size, rows.length);
assert.ok(rows.some(row => row.net === '/cpu/ANT'));
assert.ok(rows.some(row => row.net === 'GND'));
assert.ok(rows.every(row => board.pads.some(pad => pad.id === row.id && pad.net === row.net)
  || board.tracks.some(track => track.id === row.id && track.net === row.net)), 'every legend entry has netted source geometry');
assert.match(source, /viewMode === "3D" && netLegend3D\.length > 0/);
console.log(`3D board net legend: ${rows.length} distinct ESP32 nets, visible-layer and isolated-net filters, no unnetted antenna graphic attribution`);
