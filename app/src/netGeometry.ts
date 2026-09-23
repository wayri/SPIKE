import type { ParsedBoard } from "./boardParser";

export type NetGeometry = {
  contract: "spike/net-geometry/v1";
  net: string;
  technology: NonNullable<ParsedBoard["technology"]>;
  regions: NonNullable<ParsedBoard["regions"]>;
  bends: NonNullable<ParsedBoard["bendLines"]>;
  layers: string[];
  tracks: ParsedBoard["tracks"];
  zones: ParsedBoard["zones"];
  vias: ParsedBoard["vias"];
  pads: ParsedBoard["pads"];
  stackup: ParsedBoard["stackup"];
  counts: {
    tracks: number;
    zones: number;
    vias: number;
    pads: number;
  };
};

export function extractNetGeometry(board: ParsedBoard, net: string): NetGeometry {
  const tracks = board.tracks.filter((item) => item.net === net);
  const zones = board.zones.filter((item) => item.net === net);
  const vias = board.vias.filter((item) => item.net === net);
  const pads = board.pads.filter((item) => item.net === net);
  const layers = new Set<string>();
  tracks.forEach((item) => layers.add(item.layer));
  zones.forEach((item) => layers.add(item.layer));
  vias.forEach((item) => item.layers.forEach((layer) => layers.add(layer)));
  pads.forEach((item) => item.layers.forEach((layer) => {
    if (layer.endsWith(".Cu")) layers.add(layer);
  }));

  return {
    contract: "spike/net-geometry/v1",
    net,
    technology: board.technology ?? "rigid",
    regions: board.regions ?? [],
    bends: board.bendLines ?? [],
    layers: board.layers.filter((layer) => layers.has(layer)),
    tracks,
    zones,
    vias,
    pads,
    stackup: board.stackup,
    counts: {
      tracks: tracks.length,
      zones: zones.length,
      vias: vias.length,
      pads: pads.length,
    },
  };
}
