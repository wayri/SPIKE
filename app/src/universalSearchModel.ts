export type UniversalSearchableItem = {
  label: string;
  category: string;
  description?: string;
  keywords?: string;
  disabled?: boolean;
};

type IndexedField = {
  text: string;
  words: string[];
  weight: number;
};

export function normalizeSearchText(value: string) {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function tokenScore(token: string, fields: IndexedField[]) {
  let best = 0;
  for (const field of fields) {
    if (field.words.includes(token)) best = Math.max(best, field.weight);
    else if (field.words.some(word => word.startsWith(token))) best = Math.max(best, field.weight * 0.82);
    else if (field.text.includes(token)) best = Math.max(best, field.weight * 0.55);
  }
  return best;
}

export function scoreUniversalSearchItem(item: UniversalSearchableItem, query: string) {
  const term = normalizeSearchText(query);
  if (!term) return item.disabled ? -1 : 1;

  const label = normalizeSearchText(item.label);
  const category = normalizeSearchText(item.category);
  const description = normalizeSearchText(item.description ?? "");
  const keywords = normalizeSearchText(item.keywords ?? "");
  if (label === term) return 1000;
  if (label.startsWith(term)) return 850;
  if (label.includes(term)) return 700;

  const fields: IndexedField[] = [
    { text: label, words: label.split(" ").filter(Boolean), weight: 120 },
    { text: keywords, words: keywords.split(" ").filter(Boolean), weight: 95 },
    { text: category, words: category.split(" ").filter(Boolean), weight: 65 },
    { text: description, words: description.split(" ").filter(Boolean), weight: 45 },
  ];
  const tokens = term.split(" ").filter(Boolean);
  const scores = tokens.map(token => tokenScore(token, fields));
  if (scores.some(value => value === 0)) return 0;
  return scores.reduce((sum, value) => sum + value, 0) / scores.length + Math.min(tokens.length, 4) * 8;
}
