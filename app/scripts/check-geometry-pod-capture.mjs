// SPDX-License-Identifier: Apache-2.0
import {readFileSync,statSync} from 'node:fs';
import {admitGeometryPodResult} from '../src/geometryPodStudy.ts';
const path=process.argv[2];
if(!path)throw new Error('Usage: node scripts/check-geometry-pod-capture.mjs <actual-result.json>');
if(statSync(path).size>32*1024*1024)throw new Error('Serialized result file exceeds 32 MB (including whitespace).');
const result=admitGeometryPodResult(JSON.parse(readFileSync(path,'utf8')));
console.log(JSON.stringify({contract:result.contract,accepted_steps:result.accepted_steps,
  field_snapshots:result.field_snapshots?.length??0,physical_load_qualified:result.physical_load_qualified,
  capture_admission:'passed',gui_verified:false}));
