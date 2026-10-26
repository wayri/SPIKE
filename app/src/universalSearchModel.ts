// SPDX-License-Identifier: Apache-2.0
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

/** One edit/transposition for ordinary words; exact matches always rank higher. */
function nearbySearchWord(a:string,b:string):boolean {
 if(a.length<4||a.length>32||b.length<4||b.length>32||/\d/.test(a+b)||Math.abs(a.length-b.length)>1)return false;
 if(a.length===b.length){const mismatch=[...a].map((c,i)=>c===b[i]?-1:i).filter(i=>i>=0);if(mismatch.length===2&&mismatch[1]===mismatch[0]+1&&a[mismatch[0]]===b[mismatch[1]]&&a[mismatch[1]]===b[mismatch[0]])return true;}
 let i=0,j=0,edits=0;while(i<a.length&&j<b.length){if(a[i]===b[j]){i++;j++;continue;}if(++edits>1)return false;if(a.length>=b.length)i++;if(b.length>=a.length)j++;}return edits+Number(i<a.length||j<b.length)<=1;
}
function tokenScore(token: string, fields: IndexedField[]) {
  let best = 0;
  for (const field of fields) {
    if (field.words.includes(token)) best = Math.max(best, field.weight);
    else if (field.words.some(word => word.startsWith(token))) best = Math.max(best, field.weight * 0.82);
    else if (field.text.includes(token)) best = Math.max(best, field.weight * 0.55);
    else if(field.weight>=65&&field.words.some(word=>nearbySearchWord(token,word)))best=Math.max(best,field.weight*0.36);
  }
  return best;
}

type SearchIndex = { label: string; fields: IndexedField[]; source: string[] };
const itemIndexes = new WeakMap<UniversalSearchableItem, SearchIndex>();
let previousQuery: { raw: string; request: string; term: string; tokens: string[] } | undefined;

function prepareQuery(raw: string) {
  if (previousQuery?.raw === raw) return previousQuery;
  const request = raw.trim().replace(/^(?:please\s+|(?:can|could|would) you\s+|i want to\s+)/i, "");
  const term = normalizeSearchText(request.replace(/^(?:open|show|go to|take me to)\s+(?:the\s+)?/i, ""));
  return previousQuery = { raw, request, term, tokens: term.split(" ").filter(Boolean) };
}

/** Cache only presentation text; every score still reads the current enabled state. */
function indexItem(item: UniversalSearchableItem): SearchIndex {
  const source = [item.label, item.keywords ?? "", item.category, item.description ?? ""];
  const cached = itemIndexes.get(item);
  if (cached && cached.source.every((value, index) => value === source[index])) return cached;
  const weights = [120, 95, 65, 45];
  const fields = source.map((value, index) => {
    const text = normalizeSearchText(value);
    return { text, words: text.split(" ").filter(Boolean), weight: weights[index] };
  });
  const indexed = { source, label: fields[0].text, fields };
  itemIndexes.set(item, indexed);
  return indexed;
}

export function scoreUniversalSearchItem(item: UniversalSearchableItem, query: string) {
  const { request, term, tokens } = prepareQuery(query);
  if (/^show\s+/i.test(request) && /^hide\s+/i.test(item.label)) return 0;
  if (/^hide\s+/i.test(request) && /^show\s+/i.test(item.label)) return 0;
  if (!term) return item.disabled ? -1 : 1;

  const { label, fields } = indexItem(item);
  if (label === term) return 1000;
  if (label.startsWith(term)) return 850;
  if (label.includes(term)) return 700;

  const scores = tokens.map(token => tokenScore(token, fields));
  if (scores.some(value => value === 0)) return 0;
  return scores.reduce((sum, value) => sum + value, 0) / scores.length + Math.min(tokens.length, 4) * 8;
}

