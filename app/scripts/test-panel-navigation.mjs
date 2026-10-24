// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { importTestTypescript } from './import-test-typescript.mjs';

const {
  PANEL_NAVIGATION_HISTORY_LIMIT,
  canonicalPanelLocation,
  createPanelNavigationHistory,
  findPanelNavigationTarget,
  recordPanelNavigation,
} = await importTestTypescript('panelNavigationModel');

const panels = [
  { id:'setup', aliases:['legacy-setup'], open:true },
  { id:'results', aliases:['latest-results'], open:true },
  { id:'closed', open:false },
];

assert.equal(canonicalPanelLocation(panels, 'legacy-setup'), 'setup');
let history = createPanelNavigationHistory(panels, null);
history = recordPanelNavigation(history, panels, 'legacy-setup');
history = recordPanelNavigation(history, panels, 'setup');
assert.deepEqual(history, { entries:[null, 'setup'], index:1 }, 'aliases must not create duplicate visits');

history = recordPanelNavigation(history, panels, 'closed');
history = recordPanelNavigation(history, panels, 'results');
let move = findPanelNavigationTarget(history, panels, -1);
assert.equal(move?.target, 'setup', 'Back must safely skip a closed panel');
history = move.history;
move = findPanelNavigationTarget(history, panels, 1);
assert.equal(move?.target, 'results', 'Forward must safely skip a closed panel');

history = move.history;
history = findPanelNavigationTarget(history, panels, -1).history;
history = recordPanelNavigation(history, panels, null);
assert.deepEqual(history, { entries:[null, 'setup', null], index:2 }, 'a new visit after Back must truncate the forward branch');
assert.equal(findPanelNavigationTarget(history, panels, 1), null);

history = createPanelNavigationHistory(panels, null);
for(let visit=0; visit<PANEL_NAVIGATION_HISTORY_LIMIT+8; visit+=1) history=recordPanelNavigation(history, panels, visit%2?'setup':'results');
assert.equal(history.entries.length, PANEL_NAVIGATION_HISTORY_LIMIT, 'history must remain bounded');
assert.equal(history.index, PANEL_NAVIGATION_HISTORY_LIMIT-1);

console.log('Panel navigation canonicalizes aliases, skips closed visits, truncates branches, and bounds history');

assert.equal(findPanelNavigationTarget({entries:[null,'closed',null],index:2},panels,-1),null,'closed visits cannot leave a useless duplicate Board destination');
