// SPDX-License-Identifier: Apache-2.0
import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
const b=await build({stdin:{contents:"export {createProjectPackage} from './src/projectPackage'; export {normalizeSolverResult,defaultResultVisualization} from './src/analysisResults';",resolveDir:process.cwd(),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false});
const api=await import(`data:text/javascript;base64,${Buffer.from(b.outputFiles[0].text).toString('base64')}`);
const source=await readFile('../examples/emerge/antenna_example.kicad_pcb','utf8');
const records=[];
for(const [label,path] of [['EMerge solved antenna','../examples/emerge/gui_workflow/patch_fields_admitted_result.json'],['Optycal antenna + STEP reflector','../examples/optycal/admitted_result.json']]) {
 const bundle=api.normalizeSolverResult(JSON.parse(await readFile(path,'utf8'))); records.push({id:bundle.analysis_id,label,bundle});
}
const project=api.createProjectPackage({project:{name:'EM viewport example.spike'},design:{source_file:'antenna_example.kicad_pcb',source_format:'kicad_pcb',source_board:source},analysis:{latest_result:records[1].bundle,result_history:records,result_display:records[1].id,view_mode:'3D',result_visualization:api.defaultResultVisualization(),em_viewport_settings:{quantity:'installed_e',displayRadiusMm:120}},emi:{},thermal:{},probes:[]});
await writeFile('../examples/optycal/viewport_example.spike',JSON.stringify(project),'utf8');
console.log('Saved real solved antenna and reflector results with PCB for viewport review.');
