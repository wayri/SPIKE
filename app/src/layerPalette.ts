const copperPalette = [
  "#e55757", "#c965e6", "#50b9e8", "#55c98b",
  "#d8c34f", "#e78b43", "#7d83e9", "#4dc4bd",
];

export function layerCssColor(name: string, copperIndex = -1) {
  if (name === "F.Cu") return copperPalette[0];
  if (name === "B.Cu") return "#4f7fe8";
  const internalNumber = /^In(\d+)\.Cu$/i.exec(name)?.[1];
  const resolvedIndex = copperIndex >= 0 ? copperIndex : internalNumber ? Number(internalNumber) : -1;
  if (name.endsWith(".Cu") && resolvedIndex >= 0) return copperPalette[1 + Math.max(0, resolvedIndex - 1) % (copperPalette.length - 1)];
  const known: Record<string, string> = {
    "F.Mask": "#3fa27d", "B.Mask": "#287b63", "F.SilkS": "#e7e9df",
    "B.SilkS": "#aab7c1", "Edge.Cuts": "#d5bf6b", "Margin": "#b47ccc",
  };
  if (known[name]) return known[name];
  let hash = 0;
  for (const character of name) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 48% 58%)`;
}

export function layerThreeColor(name: string, copperIndex = -1) {
  return Number.parseInt(layerCssColor(name, copperIndex).replace("#", ""), 16);
}
