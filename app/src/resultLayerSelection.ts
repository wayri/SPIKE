export function resultDatumLayers(layer: string | undefined, boardLayers: string[]): string[] {
  if (!layer) return [];
  if (layer === "through") return [...boardLayers];
  const endpoints = layer.split("->").map(entry => entry.trim()).filter(Boolean);
  if (endpoints.length !== 2) return endpoints;
  const first = boardLayers.indexOf(endpoints[0]);
  const last = boardLayers.indexOf(endpoints[1]);
  if (first < 0 || last < 0) return endpoints;
  return boardLayers.slice(Math.min(first, last), Math.max(first, last) + 1);
}

export function selectedDatumLayers(
  layer: string | undefined,
  selectedLayers: string[],
  boardLayers: string[],
): string[] {
  const datumLayers = resultDatumLayers(layer, boardLayers);
  if (!selectedLayers.length) return datumLayers;
  return selectedLayers.filter(candidate => datumLayers.includes(candidate));
}

export function resultLayerMatchesSelection(
  layer: string | undefined,
  selectedLayers: string[],
  boardLayers: string[],
): boolean {
  if (!selectedLayers.length) return true;
  return selectedDatumLayers(layer, selectedLayers, boardLayers).length > 0;
}

export function resultLayerIsVisible(
  layer: string | undefined,
  selectedLayers: string[],
  boardLayers: string[],
  visibleLayers: Record<string, boolean>,
): boolean {
  const layers = selectedDatumLayers(layer, selectedLayers, boardLayers);
  if (!layers.length) return !selectedLayers.length && !layer;
  return layers.some(candidate => visibleLayers[candidate] !== false);
}

/**
 * Keep a user's explicit layer when it can show at least one admitted result.
 * Otherwise use the aggregate view so a valid inner-layer result is not
 * presented as an apparently empty analysis merely because F.Cu was selected
 * when the result became active.
 */
export function resultLayerWithVisibleData(
  samples: { layer?: string }[],
  activeLayer: string,
  boardLayers: string[],
  selectedResultLayers: string[],
  visibleLayers: Record<string, boolean>,
): string {
  if (activeLayer === "All" || activeLayer === "Overview" || !samples.length) return activeLayer;
  const visibleSamples = samples.filter(sample =>
    resultLayerIsVisible(sample.layer, selectedResultLayers, boardLayers, visibleLayers));
  if (!visibleSamples.length) return activeLayer;
  const activeHasData = visibleSamples.some(sample => {
    const layers = resultDatumLayers(sample.layer, boardLayers);
    return !layers.length || layers.includes(activeLayer);
  });
  return activeHasData ? activeLayer : "All";
}
