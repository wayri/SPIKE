// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";
const {loadAppSettings, saveAppSettings, toggleLegacyRibbon, APP_SETTINGS_STORAGE_KEY} = await importTestTypescript("appSettings");
const storage = new Map();
globalThis.localStorage = {getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)};
assert.equal(loadAppSettings().interfaceMode,"clean");
for (const mode of ["classic","clean"]) {
  saveAppSettings({...loadAppSettings(),interfaceMode:mode,ribbonVisible:mode==="classic",uiScale:.85});
  assert.equal(loadAppSettings().interfaceMode,mode);
  assert.equal(loadAppSettings().ribbonVisible,mode==="classic");
  assert.equal(loadAppSettings().uiScale,.85);
}
storage.set(APP_SETTINGS_STORAGE_KEY, JSON.stringify({interfaceMode:"unknown",chromeVersion:2,ribbonVisible:true}));
assert.equal(loadAppSettings().interfaceMode,"clean");
assert.equal(loadAppSettings().ribbonVisible,false,"old clean ribbon visibility must not reappear after migration");
for (const chromeVersion of [undefined, 2, 3]) {
  storage.set(APP_SETTINGS_STORAGE_KEY, JSON.stringify({interfaceMode:"clean",chromeVersion,ribbonVisible:true}));
  const clean = loadAppSettings();
  assert.equal(clean.ribbonVisible,false,"saved ribbon cannot reappear in Clean layout");
  assert.equal(toggleLegacyRibbon({...clean,ribbonVisible:true}).ribbonVisible,false,"shortcut cannot reopen the Classic ribbon in Clean layout");
}
const classic = {...loadAppSettings(),interfaceMode:"classic",ribbonVisible:false};
assert.equal(toggleLegacyRibbon(classic).ribbonVisible,true);
assert.equal(toggleLegacyRibbon(toggleLegacyRibbon(classic)).ribbonVisible,false);
storage.set(APP_SETTINGS_STORAGE_KEY,"bad JSON");
assert.equal(loadAppSettings().interfaceMode,"clean");
console.log("Interface preference migration, persistence and corrupt-storage recovery passed.");
