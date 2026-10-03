// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTableModule } from "./load-data-table.mjs";

const { tableRowGroups, tableSearchText, matchTableRows, tablePage, renderTableBodies } = loadTableModule("dataTableModel");
const Table = loadTableModule("DataTable").default;
const h = React.createElement;
const changes = [];
const rows = Array.from({ length: 205 }, (_, i) => h(React.Fragment, { key: `record-${i}` },
  h("tr", null, h("td", null, h("input", { value: `Load ${i}`, onChange: e => changes.push([i, e.target.value]) })),
    h("td", null, h("select", { value: "cu", onChange() {} }, h("option", { value: "cu" }, "Copper"), h("option", { value: "al" }, "Aluminum")))),
  i === 104 ? h("tr", null, h("td", { colSpan: 2 }, "Expanded details")) : null));
const children = [h("thead", { key: "head" }, h("tr", null, h("th", null, "Name"), h("th", null, "Material"))), h("tbody", { key: "body" }, rows)];
const groups = tableRowGroups(children);
assert.equal(groups.length, 205);
assert.equal(matchTableRows(groups, "copper LOAD 104").length, 1);
assert.equal(matchTableRows(groups, 'copper "LOAD 104"').length, 1);
assert.equal(matchTableRows(groups, '"Load 1"').length, 111, "quoted names do not match digits in other columns");
const splitPhrase = tableRowGroups(h("tbody", null, h("tr", { key: "split" }, h("td", null, "Load"), h("td", null, "104"))));
assert.equal(matchTableRows(splitPhrase, '"Load 104"').length, 0, "phrases must stay inside one cell");
assert.equal(matchTableRows(groups, "aluminum").length, 0, "unselected options must not make every row match");
assert.equal(matchTableRows(groups, "does not match", groups[104].key)[0].key, groups[104].key, "keep focused edits mounted");
assert.match(tableSearchText(h("span", { "data-search-text": "explicit custom renderer" })), /explicit custom renderer/);
assert.equal(tableSearchText(h("input", { type: "checkbox", checked: false, onChange() {} })), "disabled");
assert.match(tableSearchText(h("select", { value: "b", onChange() {} }, h("optgroup", { label: "Group" }, h("option", { value: "b" }, "Board")))), /Board/);
const page = tablePage(groups, 1, 100);
assert.equal(page.rows.length, 100);
assert.equal(page.rows[0].key, groups[100].key);
assert.equal(tablePage(groups.slice(0, 99), 2, 100).page, 0, "deleting the last page clamps to available rows");
assert.equal(tablePage(groups, 0, NaN).rows.length, 100);
assert.equal(tablePage(groups, 0, 0).rows.length, 1);
const filtered = renderTableBodies(children, matchTableRows(groups, "Load 104"));
const html = renderToStaticMarkup(h("table", null, filtered));
assert.match(html, /Expanded details/);
assert.equal((html.match(/<tr\b/g) ?? []).length, 3, "header plus record plus its detail row");
// Filtered cells keep their original callback closure, not their visible index.
const visit = node => !node || typeof node !== "object" ? [] : Array.isArray(node) ? node.flatMap(visit) : [node, ...visit(node.props?.children)];
visit(filtered).find(node => node.type === "input").props.onChange({ target: { value: "Updated" } });
assert.deepEqual(changes, [[104, "Updated"]]);
const full = renderToStaticMarkup(h(Table, { label: "Loads" }, children));
assert.equal((full.match(/<tr\b/g) ?? []).length, 101, "large tables mount only one page of controls");
assert.match(full, /Page 1 of 3/);
assert.match(full, /205/);
assert.match(full, /aria-label="Find in Loads"/);
assert.match(full, /aria-pressed="false"/);
assert.match(renderToStaticMarkup(h(Table, { label: "Empty", emptyMessage: "Add a load." }, h("tbody"))), /Add a load/);
assert.ok(!renderToStaticMarkup(h(Table, { label: "Pre-filtered", searchable: false }, children)).includes('type="search"'));
for (const theme of ["professional-dark", "light", "high-contrast", "system"]) {
  const themed = renderToStaticMarkup(h(Table, { label: "Themed", theme }, children));
  assert.match(themed, new RegExp(`data-table-theme="${theme}"`));
  assert.doesNotMatch(themed, /<table[^>]*\btheme=/, "theme belongs to the wrapper, not a native table attribute");
}
assert.ok(!full.includes("data-table-theme="), "tables inherit the application theme by default");
console.log("Shared table filtering, identity, grouped details, bounded rendering, pagination recovery and empty states passed.");
