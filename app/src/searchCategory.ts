// SPDX-License-Identifier: Apache-2.0
/** Presentation only: category colors never imply solver readiness or validation. */
export function searchCategory(category: string): string {
  const text = category.toLowerCase();
  if (/thermal|temperature|heat/.test(text)) return "thermal";
  if (/\bcfd\b|\bcht\b|airflow|fluid/.test(text)) return "flow";
  if (/\bpi\b|power integrity|pdn/.test(text)) return "pi";
  if (/\bsi\b|\bhf\b|signal integrity|\brf\b/.test(text)) return "si";
  if (/\bem\b|electromagnetic|antenna/.test(text)) return "em";
  if (/solver|simulation|analysis|solve/.test(text)) return "solver";
  if (/mesh/.test(text)) return "mesh";
  if (/result|report|plot|dataset|stud/.test(text)) return "results";
  if (/example|tutorial|help|guide/.test(text)) return "help";
  if (/setting|preference|application/.test(text)) return "settings";
  if (/project|file|import|export/.test(text)) return "project";
  if (/assembly|harness|mcad|board|component|design|layer|net|pad|via/.test(text)) return "design";
  if (/view|workspace|navigation/.test(text)) return "view";
  return "action";
}
