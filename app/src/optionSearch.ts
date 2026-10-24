// SPDX-License-Identifier: Apache-2.0
const fold = (text: string) => text.normalize("NFKC").toLowerCase();

/** Case-insensitive AND terms; * matches any span and ? one Unicode character.
 * No regular expression evaluation, and filtering never chooses a value.
 */
export function optionMatchesQuery(text: string, query: string): boolean {
  const haystack = [...fold(text)];
  return fold(query).trim().split(/\s+/u).filter(Boolean).every(term => {
    if (!/[*?]/u.test(term)) return haystack.join("").includes(term);
    const pattern = [...`*${term.replace(/\*+/g, "*")}*`];
    let at = 0, token = 0, star = -1, restart = 0;
    while (at < haystack.length) {
      if (pattern[token] === "?" || pattern[token] === haystack[at]) { token++; at++; }
      else if (pattern[token] === "*") { star = token++; restart = at; }
      else if (star >= 0) { token = star + 1; at = ++restart; }
      else return false;
    }
    while (pattern[token] === "*") token++;
    return token === pattern.length;
  });
}

export type SelectChoice = { index: number; value: string; label: string; group: string; disabled: boolean };
export function selectChoices(select: HTMLSelectElement): SelectChoice[] {
  return Array.from(select.options).flatMap((option, index) => {
    const group = option.parentElement?.tagName === "OPTGROUP" ? option.parentElement as HTMLOptGroupElement : null;
    if (option.hidden || group?.hidden) return [];
    return [{ index, value: option.value, label: option.label || option.textContent || option.value,
      group: group?.label ?? "", disabled: select.disabled || select.matches(":disabled") || option.disabled || !!group?.disabled }];
  });
}

export function commitSelectChoice(select: HTMLSelectElement, choice: SelectChoice): boolean {
  const current = selectChoices(select).find(item => item.index === choice.index);
  if (!select.isConnected || select.disabled || select.matches(":disabled") || !current || current.disabled || current.value !== choice.value) return false;
  if (select.selectedIndex !== choice.index) {
    select.selectedIndex = choice.index;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }
  return true;
}
