// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const built=await build({entryPoints:['src/scriptViewportImport.ts'],bundle:true,write:false,format:'esm',platform:'node'});
const {completedScriptViewportRun}=await import('data:text/javascript;base64,'+Buffer.from(built.outputFiles[0].contents).toString('base64'));
const view={contract:'spike/data-view/v1',id:'11111111-1111-4111-8111-111111111111',kind:'spatial',title:'Actual E',provenance:'test',quantity:'Ey',coordinate_unit:'m',value_unit:'V/m',samples:[{x:1,y:2,z:3,value_real:3,value_imag:-4}]};
const result={contract:'spike/python-script-result/v1',status:'completed',return_code:0,views:[view]};
assert.deepEqual(completedScriptViewportRun(result,'actual solve'),{label:'actual solve',views:[view]});
for(const invalid of [null,{}, {...result,status:'failed'},{...result,return_code:1},{...result,views:[]},{...result,views:[{...view,samples:[{x:Infinity,y:0,z:0,value_real:1,value_imag:0}]}]}]) assert.throws(()=>completedScriptViewportRun(invalid,'test'));
console.log('Viewport imports require a completed zero-exit result and admit finite original spatial samples.');
