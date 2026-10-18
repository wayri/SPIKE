// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import ts from "typescript";
import {importTestTypescript} from "./import-test-typescript.mjs";

const storage = new Map();
globalThis.localStorage = {getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)};
const {loadAppSettings,saveAppSettings,APP_SETTINGS_STORAGE_KEY}=await importTestTypescript("appSettings");
assert.equal(loadAppSettings().quickToolsVisible,false);
storage.set(APP_SETTINGS_STORAGE_KEY,JSON.stringify({quickToolsVisible:"true"}));
assert.equal(loadAppSettings().quickToolsVisible,false,"only explicit boolean opt-in is admitted");
saveAppSettings({...loadAppSettings(),quickToolsVisible:true});
assert.equal(loadAppSettings().quickToolsVisible,true);
saveAppSettings({...loadAppSettings(),quickToolsVisible:false});
assert.equal(loadAppSettings().quickToolsVisible,false);

const jsx=(type,props)=>({type,props:props??{}}), module={exports:{}};
const compiled=ts.transpileModule(readFileSync(new URL("../src/ViewportEssentialTools.tsx",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function("require","module","exports",compiled)(name=>name==="react/jsx-runtime"?{jsx,jsxs:jsx}:{},module,module.exports);
const calls=[];
const render=(mode="3D")=>module.exports.default({viewMode:mode,navigationMode:"orbit",selectionFilter:"net",onMode:v=>calls.push(["mode",v]),onNavigation:v=>calls.push(["navigation",v]),onCamera:v=>calls.push(["camera",v]),onFilter:v=>calls.push(["filter",v])});
const flatten=node=>!node||typeof node!=="object"?[]:[node,...[node.props?.children].flat(Infinity).flatMap(flatten)];
const nodes=flatten(render());
const named=name=>nodes.find(node=>node.props["aria-label"]===name);
named("Pan").props.onClick(); named("Orbit").props.onClick();named("Fit scene").props.onClick();named("2D view").props.onClick();
named("Camera view").props.onChange({target:{value:"iso"}});
named("Selection filter").props.onChange({target:{value:"part"}});
assert.deepEqual(calls,[["navigation","pan"],["navigation","orbit"],["camera","fit"],["mode","2D"],["camera","view-iso"],["filter","part"]]);
assert.equal(named("Orbit").props["aria-pressed"],true);
const twoD=flatten(render("2D"));
assert.equal(twoD.find(node=>node.props["aria-label"]==="Orbit").props.disabled,true);
assert.equal(twoD.find(node=>node.props["aria-label"]==="Camera view").props.disabled,true);
assert.equal(twoD.find(node=>node.props["aria-label"]==="Pan").props["aria-pressed"],true);
console.log("Viewport essentials: explicit opt-in persistence, camera/filter routing, 2D restrictions and named icon controls passed.");
