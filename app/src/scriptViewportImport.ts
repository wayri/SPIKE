// SPDX-License-Identifier: Apache-2.0
import {admitDataViews, type DataView} from './scriptDataViews';
export type ScriptViewportRun = {label:string;views:DataView[]};
export function completedScriptViewportRun(value:unknown,label:string):ScriptViewportRun {
 const result=value as {contract?:unknown;status?:unknown;return_code?:unknown;views?:unknown};
 if(!result||result.contract!=='spike/python-script-result/v1'||result.status!=='completed'||result.return_code!==0)throw Error('Choose a successfully completed SPIKE Python result file.');
 const views=admitDataViews(result.views);
 if(!views.length)throw Error('No supported numeric views are available in this result.');
 return {label:label.slice(0,200),views};
}
