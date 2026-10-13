// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { MeshStandardMaterial } from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { applyNetFocusColor } = await importTestTypescript("netFocusMaterial");
const material = new MeshStandardMaterial({color:0xe63946,opacity:.45,transparent:true});
applyNetFocusColor(material,true); assert.equal(material.color.getHex(),0x667076);
applyNetFocusColor(material,true); applyNetFocusColor(material,false);
assert.equal(material.color.getHex(),0xe63946); assert.equal(material.opacity,.45);
material.dispose(); console.log("Net focus original material color restoration passed");
