import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(import.meta.url),cache=new Map();
function load(file){
 if(cache.has(file))return cache.get(file);
 const output=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const mod={exports:{}};cache.set(file,mod.exports);
 new Function('require','module','exports',output)(name=>{
  if(!name.startsWith('.'))return require(name);
  const base=path.resolve(path.dirname(file),name);return load(['.ts','.tsx'].map(ext=>base+ext).find(p=>fs.existsSync(p))??base);
 },mod,mod.exports);cache.set(file,mod.exports);return mod.exports;
}
const {helpTopics,helpFeatureCoverage}=load(path.join(root,'src/HelpTopics.tsx'));
const topics=helpTopics();const ids=new Set(topics.map(t=>t.id));
assert.equal(ids.size,topics.length);assert.equal(helpFeatureCoverage.length,17);
for(const row of helpFeatureCoverage){assert.ok(row.pictured&&row.gap);assert.ok(ids.has(row.topic)||row.topic.startsWith('doc:')&&fs.existsSync(path.resolve(root,'..',row.topic.slice(4))));}
for(const id of ['picture-guide','recorded-pic-dc','feature-coverage']){
 const topic=topics.find(t=>t.id===id);assert.ok(topic);
 const rendered=renderToStaticMarkup(React.createElement(React.Fragment,null,topic.body));
 for(const match of rendered.matchAll(/data-help-topic="([^"]+)"/g))assert.ok(ids.has(match[1])||match[1]==='evidence'||match[1].startsWith('doc:')&&fs.existsSync(path.resolve(root,'..',match[1].slice(4))));
 for(const match of rendered.matchAll(/src="(\/help\/[^\"]+)"/g))assert.ok(fs.existsSync(path.join(root,'public',match[1])));
 if(id==='picture-guide'){assert.equal((rendered.match(/<img /g)??[]).length,4);assert.match(rendered,/procedural/);assert.match(rendered,/not simulations/);assert.match(rendered,/ANALYSIS NOT RUN/);}
 if(id==='recorded-pic-dc'){assert.match(rendered,/completed \/ approximate/);assert.match(rendered,/16.382762821/);assert.match(rendered,/49 excluded/);assert.match(rendered,/separate local PI-only evaluation/);}
}
const center=fs.readFileSync(path.join(root,'src/HelpCenter.tsx'),'utf8');assert.match(center,/data-help-topic/);assert.match(center,/navigate\(link.dataset.helpTopic\)/);
console.log('Help picture workflows: 4 unchanged captures, 17 linked feature families, honest recordedDC provenance/status, existing assets and destinations passed');
