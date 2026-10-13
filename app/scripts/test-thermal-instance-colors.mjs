// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.SPIKE_PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({headless:true,executablePath:process.env.SPIKE_TEST_CHROME,args:['--use-angle=swiftshader','--allow-file-access-from-files']});
try {
  const page=await browser.newPage();
  await page.goto(process.env.SPIKE_TEST_URL || new URL('./fixtures/thermal-cell-color.html',import.meta.url).href);
  await page.waitForFunction(()=>window.evidence);
  const evidence=await page.evaluate(()=>window.evidence);
  assert.deepEqual(evidence.old.map(p=>p.slice(0,3)),[[0,0,0],[0,0,0]],'Fixture must reproduce the missing geometry-color defect');
  assert.deepEqual(evidence.fixed.map(p=>p.slice(0,3)),[[0,0,255],[255,0,0]],'Each cell must retain its distinct instance color');
  console.log('Thermal instance colors: reproduced black tiles; corrected red/blue pixels.',JSON.stringify(evidence));
} finally {await browser.close();}
