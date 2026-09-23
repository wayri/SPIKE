// Compiler-backed inventory: every JSX control site, including dynamic labels.
// Kept separate from explanatory guides so incomplete static labels are explicit.
import ts from 'typescript';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const controls = [];
const clean = s => s.replace(/\s+/g, ' ').trim();
const literal = n => {
  if (!n) return '';
  if (ts.isStringLiteralLike(n) || ts.isJsxText(n)) return clean(n.text);
  if (ts.isJsxExpression(n)) return literal(n.expression);
  if (ts.isConditionalExpression(n)) return [literal(n.whenTrue), literal(n.whenFalse)].filter(Boolean).join(' / ');
  return '';
};
for (const file of fs.readdirSync(path.join(root, 'src')).filter(f => f.endsWith('.tsx') && !/^(Help|help)/.test(f)).sort()) {
  const source = ts.createSourceFile(file, fs.readFileSync(path.join(root, 'src', file), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const visit = node => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const kind = node.tagName.getText(source);
      if (['button', 'input', 'select', 'textarea', 'Tool', 'MenuItem', 'Numeric', 'NumberField', 'TextField'].includes(kind)) {
        const attrs = Object.fromEntries(node.attributes.properties.filter(ts.isJsxAttribute).map(a => [a.name.getText(source), a.initializer]));
        const children = ts.isJsxElement(node.parent) ? node.parent.children : [];
        const strings = children.map(literal).filter(Boolean).join(' ');
        let parent = node.parent, section = '', fieldLabel = '';
        while (parent && !ts.isSourceFile(parent)) {
          if (ts.isJsxElement(parent)) {
            const tag = parent.openingElement.tagName.getText(source);
            if (tag === 'label' && !fieldLabel) fieldLabel = parent.children.map(literal).filter(Boolean).join(' ');
            if (tag === 'ToolGroup' && !section) section = literal(parent.openingElement.attributes.properties.find(a => ts.isJsxAttribute(a) && a.name.getText(source) === 'label')?.initializer);
          }
          if (ts.isCaseClause(parent) && !section) section = literal(parent.expression);
          parent = parent.parent;
        }
        const label = literal(attrs.label) || literal(attrs['aria-label']) || strings || fieldLabel || literal(attrs.title) || literal(attrs.placeholder) || literal(attrs.name);
        const title = literal(attrs.title);
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        const disabled = attrs.disabled ? clean(attrs.disabled.getText(source)).replace(/^\{|\}$/g, '') : '';
        const options = children.filter(ts.isJsxElement).filter(n => n.openingElement.tagName.getText(source) === 'option').map(n => n.children.map(literal).join('')).filter(Boolean);
        controls.push({id: `${file}:${line}:${node.getStart(source)}`, file, line, kind, section,
          label: label || 'Context-dependent control', dynamic: !label, description: title,
          options, disabled, min: literal(attrs.min), max: literal(attrs.max), step: literal(attrs.step),
          inputType: literal(attrs.type)});
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}
const output = JSON.stringify(controls, null, 2) + '\n';
const destination = path.join(root, 'src/helpControls.generated.json');
if (process.argv.includes('--check')) {
  if (!fs.existsSync(destination) || fs.readFileSync(destination, 'utf8') !== output) throw new Error('Help control inventory is stale; run npm run help:generate');
} else fs.writeFileSync(destination, output);
console.log(`${controls.length} control sites inventoried (${controls.filter(c => c.dynamic).length} require runtime context).`);
