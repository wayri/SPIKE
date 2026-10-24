// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { Eye, EyeOff, Focus, Layers3, Menu, PanelLeft, PanelRight, Search, X } from "./icons";
import type { ParsedLayerDefinition, ParsedStackupLayer } from "./boardParser";
import { buildLayerManagerInventory, LAYER_INVENTORY_GROUP_ORDER } from "./layerInventory";
import { layerCssColor } from "./layerPalette";
import { stackupColor } from "./stackupVisual";

type LayerName = string;

type LayerManagerBaseProps = {
  definitions: ParsedLayerDefinition[];
  stackup: ParsedStackupLayer[];
  layers: Record<LayerName, boolean>;
  opacity: Record<LayerName, number>;
  toggleLayer: (layer: LayerName) => void;
  setLayersVisible: (layers: LayerName[], visible: boolean) => void;
  showOnlyLayer: (layer: LayerName) => void;
  changeOpacity: (layer: LayerName, opacity: number) => void;
  beginOpacityChange: () => void;
  restoreDefaults: () => void;
};

type LayerManagerSceneProps = {
  showSceneControls?: true;
  viaCount: number;
  showNetNames: boolean;
  setShowNetNames: (value: boolean) => void;
  showVias: boolean;
  setShowVias: (value: boolean) => void;
  showOnlyVias: () => void;
  layerSeparation: number;
  setLayerSeparation: (value: number) => void;
  showModels: boolean;
  setShowModels: (value: boolean) => void;
  showSmdModels: boolean;
  setShowSmdModels: (value: boolean) => void;
  showThtModels: boolean;
  setShowThtModels: (value: boolean) => void;
  smdCount: number;
  thtCount: number;
};

type LayerManagerWithoutSceneProps = {
  showSceneControls: false;
};

type LayerManagerShellProps =
  | { embedded: true; onClose?: () => void }
  | { embedded?: false; onClose: () => void };

export type LayerManagerProps = LayerManagerBaseProps
  & (LayerManagerSceneProps | LayerManagerWithoutSceneProps)
  & LayerManagerShellProps;

export default function LayerManager(props: LayerManagerProps) {
  const {
    definitions, stackup, layers, opacity, toggleLayer, setLayersVisible,
    showOnlyLayer, changeOpacity, beginOpacityChange, restoreDefaults,
  } = props;
  const embedded = props.embedded === true;
  const [query, setQuery] = useState("");
  const [dockPosition, setDockPosition] = useState<"right" | "left" | "float">("right");
  const inventory = useMemo(() => buildLayerManagerInventory(definitions, stackup), [definitions, stackup]);
  const filtered = inventory.entries.filter(entry =>
    `${entry.name} ${entry.description} ${entry.group}`.toLowerCase().includes(query.trim().toLowerCase()));
  const groups = LAYER_INVENTORY_GROUP_ORDER
    .map(name => ({ name, layers: filtered.filter(layer => layer.group === name) }))
    .filter(group => group.layers.length);
  const visibleCount = inventory.drawableNames.filter(name => layers[name] !== false).length;
  const shellStyle = embedded ? {
    width: "100%", height: "100%", maxHeight: "none",
    gridTemplateRows: props.showSceneControls === false
      ? "auto auto auto minmax(120px, 1fr)"
      : undefined,
  } : undefined;

  return <div className={embedded ? "layer-manager embedded" : `floating-panel layer-manager dock-${dockPosition}`} style={shellStyle}>
    {!embedded && <button className="panel-dock-toggle" onClick={() => setDockPosition(current => current === "right" ? "left" : current === "left" ? "float" : "right")} title={`Layer manager: ${dockPosition} (click to ${dockPosition === "right" ? "dock left" : dockPosition === "left" ? "float" : "dock right"})`}>{dockPosition === "right" ? <PanelRight size={14} /> : dockPosition === "left" ? <PanelLeft size={14} /> : <Menu size={14} />}</button>}
    <div className="floating-heading" style={embedded ? { cursor: "default" } : undefined}><div><b>LAYER MANAGER</b><small>{inventory.copperCount} copper · {inventory.physicalCount} stack rows · {inventory.drawableCount} drawable · {visibleCount} visible</small></div>{!embedded && <button onClick={props.onClose} title="Close layer manager"><X size={15} /></button>}</div>
    <div className="layer-search"><Search size={14} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Find layer" aria-label="Find layer" />{query && <button onClick={() => setQuery("")} title="Clear search"><X size={13} /></button>}</div>
    <div className="layer-actions">
      <button onClick={() => setLayersVisible(inventory.drawableNames, true)} title="Show all drawable layers"><Eye size={14} /> All on</button>
      <button onClick={() => setLayersVisible(inventory.drawableNames, false)} title="Hide all drawable layers"><EyeOff size={14} /> All off</button>
      <button onClick={restoreDefaults} title="Restore imported layer defaults"><Layers3 size={14} /> Reset</button>
    </div>
    <div className="layer-list">
      {groups.map(group => {
        const names = group.layers.filter(layer => layer.drawable).map(layer => layer.name);
        const allVisible = names.every(name => layers[name] !== false);
        return <section className="layer-group" key={group.name}>
          <div className="layer-group-heading">{names.length ? <button onClick={() => setLayersVisible(names, !allVisible)} title={`${allVisible ? "Hide" : "Show"} ${group.name} layers`}>{allVisible ? <Eye size={13} /> : <EyeOff size={13} />}</button> : <i className="physical-group-marker"><Layers3 size={12} /></i>}<b>{group.name}</b><span>{group.layers.length}</span></div>
          {group.layers.map(layer => {
            const visible = layers[layer.name] !== false;
            const value = opacity[layer.name] ?? 1;
            return <div className={`layer-row ${layer.drawable && !visible ? "hidden-layer" : ""} ${layer.drawable ? "" : "physical-only"}`} key={layer.key}>
              {layer.drawable ? <button className="layer-eye" onClick={() => toggleLayer(layer.name)} title={`${visible ? "Hide" : "Show"} ${layer.name}`}>{visible ? <Eye size={15} /> : <EyeOff size={15} />}</button> : <span className="physical-layer-marker" title="Physical stack layer; no independent drawable surface"><Layers3 size={13} /></span>}
              <i className="layer-color" style={{ backgroundColor: layer.stackup ? stackupColor(layer.stackup) : layer.name === "Board body" ? "#75552c" : layer.drawable ? layerCssColor(layer.name) : "#927a55" }} />
              <div className="layer-identity"><b>{layer.name}</b><span>{layer.description}</span></div>
              {layer.drawable ? <><button className="layer-only" onClick={() => showOnlyLayer(layer.name)} title={`Show only ${layer.name}`}><Focus size={14} /></button><input className="layer-opacity" type="range" min="0" max="100" value={Math.round(value * 100)} disabled={!visible} onPointerDown={beginOpacityChange} onChange={event => changeOpacity(layer.name, Number(event.target.value) / 100)} title={`${Math.round(value * 100)}% opacity`} aria-label={`${layer.name} opacity`} /><output>{Math.round(value * 100)}%</output></> : <span className="physical-layer-note">STACK</span>}
            </div>;
          })}
        </section>;
      })}
      {!groups.length && <div className="layer-empty">No layers match “{query}”.</div>}
    </div>
    {props.showSceneControls !== false && <div className="scene-controls">
      <div className="scene-heading"><span>SCENE</span><small>{props.layerSeparation > 0 ? "EXPLODED LAYER VIEW" : "ASSEMBLED"}</small><button onClick={() => { beginOpacityChange(); props.setLayerSeparation(props.layerSeparation > 0 ? 0 : 3); }}>{props.layerSeparation > 0 ? "Collapse" : "Explode"}</button></div>
      <div className="scene-row"><Layers3 size={14} /><div><b>Layer separation</b><span>Physical spacing between copper layers</span></div><input type="range" min="0" max="12" step="0.5" value={props.layerSeparation} onPointerDown={beginOpacityChange} onChange={event => props.setLayerSeparation(Number(event.target.value))} aria-label="Layer separation" title={`${props.layerSeparation.toFixed(1)} mm layer separation`} /><output>{props.layerSeparation.toFixed(1)} mm</output></div>
      <div className="scene-row"><button className="layer-eye" aria-pressed={props.showNetNames} onClick={() => { beginOpacityChange(); props.setShowNetNames(!props.showNetNames); }} title="Toggle net names on 2D traces and zones">{props.showNetNames ? <Eye size={15} /> : <EyeOff size={15} />}</button><div><b>Net names</b><span>2D traces and zones; zoom in for fine traces</span></div></div>
      <div className="scene-row"><button className="layer-eye" onClick={() => { beginOpacityChange(); props.setShowVias(!props.showVias); }} title={`${props.showVias ? "Hide" : "Show"} vias`}>{props.showVias ? <Eye size={15} /> : <EyeOff size={15} />}</button><div><b>Plated vias</b><span>{props.viaCount} barrels and annular rings</span></div><button className="scene-only" onClick={props.showOnlyVias} title="Show only vias"><Focus size={14} /></button></div>
      <div className="scene-row"><button className="layer-eye" onClick={() => { beginOpacityChange(); props.setShowModels(!props.showModels); }} title={`${props.showModels ? "Hide" : "Show"} all 3D component models`}>{props.showModels ? <Eye size={15} /> : <EyeOff size={15} />}</button><div><b>All 3D component models</b><span>Resolved KiCad models with native fallbacks for unresolved references</span></div></div>
      <div className={`scene-row ${props.showModels && props.showSmdModels ? "" : "scene-disabled"}`}><button className="layer-eye" disabled={!props.showModels} onClick={() => { beginOpacityChange(); props.setShowSmdModels(!props.showSmdModels); }} title={`${props.showSmdModels ? "Hide" : "Show"} SMD component models`}>{props.showModels && props.showSmdModels ? <Eye size={15} /> : <EyeOff size={15} />}</button><div><b>SMD models</b><span>{props.smdCount} surface-mount components</span></div></div>
      <div className={`scene-row ${props.showModels && props.showThtModels ? "" : "scene-disabled"}`}><button className="layer-eye" disabled={!props.showModels} onClick={() => { beginOpacityChange(); props.setShowThtModels(!props.showThtModels); }} title={`${props.showThtModels ? "Hide" : "Show"} through-hole component models`}>{props.showModels && props.showThtModels ? <Eye size={15} /> : <EyeOff size={15} />}</button><div><b>Through-hole models</b><span>{props.thtCount} drilled-footprint components</span></div></div>
    </div>}
  </div>;
}
