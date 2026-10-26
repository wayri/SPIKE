// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, unlinkSync, rmdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { emResistorChtStudyRunner, selectedEmResistorChtStudy } = await importTestTypescript("emResistorChtStudy");
const { normalizeStudies, updateStudyCase } = await importTestTypescript("simulationStudies");
const { mergeProjectSnapshot } = await importTestTypescript("projectSnapshotState");
const python = process.env.PYTHON || resolve("../.venv/Scripts/python.exe");
const directory = mkdtempSync(join(tmpdir(), "spike-g02-"));
const files = [];
function file(name) { const path=join(directory,name); files.push(path); return path; }
function execute(code, expected=0) {
  const result=spawnSync(python,["-"],{input:code,cwd:resolve(".."),encoding:"utf8",env:{...process.env,OPENBLAS_NUM_THREADS:"1",OMP_NUM_THREADS:"1",MKL_NUM_THREADS:"1"}});
  assert.equal(result.status,expected,result.error?.message ?? result.stderr); return result.stdout;
}
try {
  const requestFile=file("request.json"), studyFile=file("study.json");
  writeFileSync(requestFile,execute('import json; from tests.python.test_em_network_resistor_cht import request; print(json.dumps({"request":request(1)[0]}))'));
  const context=`from python.spike_core.service_em_cosimulation import handle_em_cosimulation_request
class Spike:
    def call(self, method, params):
        response = handle_em_cosimulation_request(method, params)
        if not response or not response.get("ok"):
            raise ValueError(str(response))
        return response["result"]
spike = Spike()
`;
  const source=emResistorChtStudyRunner().replace("REQUEST_FILE = None",`REQUEST_FILE = ${JSON.stringify(requestFile)}`).replace("STUDY_FILE = None",`STUDY_FILE = ${JSON.stringify(studyFile)}`);
  execute(context+source);
  const saved=JSON.parse(readFileSync(studyFile,"utf8"));
  const normalized=normalizeStudies(saved.cases ? [saved] : saved)[0];
  const item=normalized.cases[0];
  assert.deepEqual(item.settings.request,JSON.parse(readFileSync(requestFile,"utf8")).request);
  assert.equal(item.resultSnapshot.production_qualified,false);
  assert.equal(item.runs.length,1);
  assert.equal(JSON.stringify(normalizeStudies(JSON.parse(JSON.stringify([normalized])))),JSON.stringify([normalized]),
    "JSON round-trip preserves canonical values (JSON represents negative zero as zero)");
  for(const change of [
    request=>{request.ac_request.boundaries[0].p0.voltage_v[0]=25;},
    request=>{request.cht_request.energy.materials.solid.conductivity_w_mk=3;},
    request=>{request.cht_request.energy.boundaries.xmin.temperature_k[0]=310;},
    request=>{request.cht_request.mesh.vertices[0][0]+=0.01;},
  ]) {
    const request=structuredClone(item.settings.request);
    change(request);
    const edited=updateStudyCase(normalized,item.id,{settings:{request}});
    assert.equal(edited.cases[0].resultSnapshot,undefined);
    assert.deepEqual(edited.cases[0].runs,item.runs);
    const merged=mergeProjectSnapshot({studies:[normalized]},{studies:[edited]});
    assert.equal(merged.studies[0].cases[0].resultSnapshot,undefined);
  }
  const renamed=updateStudyCase(normalized,item.id,{name:"Annotated reference",notes:"Display only"});
  assert.deepEqual(renamed.cases[0].resultSnapshot,item.resultSnapshot);
  assert.equal(selectedEmResistorChtStudy(normalized,item).cases.length,1);
  assert.deepEqual(selectedEmResistorChtStudy(normalized,{...item,settings:{request:{forged:true}}}).cases[0],item,
    "selection uses the saved authoritative row rather than a caller-supplied replacement");
  assert.deepEqual(selectedEmResistorChtStudy(normalized,item,item.runs[0]).cases[0].settings,item.runs[0].settings);
  assert.throws(()=>normalizeStudies([{...normalized,notes:"x".repeat(3*1024*1024)}]),/3 MiB/);
  assert.throws(()=>selectedEmResistorChtStudy({...normalized,cases:[item,item]},item),/Select one/);
  const replayFile=file("replay.json");
  execute(context+emResistorChtStudyRunner(normalized).replace("STUDY_FILE = None",`STUDY_FILE = ${JSON.stringify(replayFile)}`));
  assert.equal(JSON.parse(readFileSync(replayFile,"utf8")).cases[0].runs.length,2);
  const defaultContext='class Spike:\n def call(self,*args): raise RuntimeError("Unexpected worker call")\nspike=Spike()\n';
  assert.match(execute(defaultContext+emResistorChtStudyRunner()),/nothing was launched/);
  execute(context+source,1); // Existing export is refused, never overwritten.
  assert.deepEqual(JSON.parse(readFileSync(studyFile,"utf8")),saved);
  console.log("AC/CHT actual worker runner, study round-trip, immutable history, project merge, replay and export collision checks passed.");
} finally {
  for(const path of files) {try{unlinkSync(path);}catch{}}
  rmdirSync(directory);
}
