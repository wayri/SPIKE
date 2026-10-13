// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {importTestTypescript} from "./import-test-typescript.mjs";
const {createMcpAnalysisConversation}=await importTestTypescript("mcpAnalysisConversation");
const design={contract:"spike/v1",design_id:"board",components:[{id:"r1",reference:"R1"}]},canonical={contract:"spike/design-ir/v2",design_id:"canonical"};
let context={design,canonicalDesign:canonical,activeDesignId:"board"};const calls=[];let release;
const helper=createMcpAnalysisConversation({getContext:()=>context,callWorker:async request=>{calls.push(request);if(request.method==="query_spider"&&request.params.name_contains==="hold")await new Promise(resolve=>release=resolve);return {ok:true,result:{contract:"spider/api-result/v1",method:request.method,ok:true,document_revision:"a".repeat(64),entities:[]}};}});
const revision=helper.getRevision();const inspected=await helper.handle("spider_context",{});
assert.equal(calls[0].method,"validate_spider");assert.equal(calls[0].params.document,canonical);assert.equal(inspected.readOnly,true);assert.equal(helper.getRevision(),revision,"inspection cannot mutate prepared cases");
await helper.handle("spider_query",{query:{entity_types:["components"],limit:10,expected_revision:"a".repeat(64)}});
assert.deepEqual(calls.at(-1).params.entity_types,["components"]);assert.equal(calls.at(-1).params.document,canonical);
await assert.rejects(helper.handle("spider_query",{query:{method:"run_python_script"}}),/Unknown/);
await assert.rejects(helper.handle("spider_query",{document:{}}),/Unknown/);
await helper.handle("spider_compare",{before:design,query:{limit:2}});assert.equal(calls.at(-1).method,"compare_spider");assert.equal(calls.at(-1).params.after,canonical);
const pending=helper.handle("spider_query",{query:{name_contains:"hold"}});while(!release)await new Promise(resolve=>setTimeout(resolve,1));context={...context,activeDesignId:"other"};release();await assert.rejects(pending,/changed/);
context={...context,activeDesignId:"board"};await helper.handle("studio_board_context",{});assert.equal(calls.at(-1).method,"prepare_studio_board_context");assert.equal(calls.at(-1).params.design,design);
const described=await helper.handle("analysis_describe",{kind:"studio_feedback"});assert.equal(described.analyses.studio_feedback.method,"run_studio_board_cosimulation");assert.equal(described.analyses.studio_feedback.schema,"studio-board-feedback-request-v1.schema.json");
console.log("MCP SpiDeR interfaces: canonical source, bounded filter routing, read-only revision, stale response rejection and Studio context passed");
