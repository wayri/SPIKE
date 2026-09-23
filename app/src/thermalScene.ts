export type ThermalPoint3 = [number, number, number];
export type ThermalCoordinateFrame = "domain_local" | "board_local" | "board_absolute";

export type ThermalFan = {
  id: string;
  name: string;
  enabled: boolean;
  position: ThermalPoint3;
  direction: ThermalPoint3;
  diameter_mm: number;
  depth_mm: number;
  flow_rate_m3_s: number;
  static_pressure_pa: number;
  rpm: number;
};

export type ThermalHeatsink = {
  id: string;
  name: string;
  enabled: boolean;
  target: string;
  position: ThermalPoint3;
  dimensions_mm: { x: number; y: number; z: number };
  material: string;
  interface_resistance_c_per_w: number;
  fin_count: number;
  fin_thickness_mm: number;
  fin_height_mm: number;
};

export type ThermalSceneVisibility = {
  volume: boolean;
  heatSources: boolean;
  airflow: boolean;
  hardware: boolean;
  /** Optional for project/UI compatibility; a completed field is visible by default. */
  field?: boolean;
};

export const defaultThermalSceneVisibility: ThermalSceneVisibility = {
  volume: true,
  heatSources: true,
  airflow: true,
  hardware: true,
  field: true,
};

export type ThermalScenarioView = {
  contract?: string;
  solver?: { engine?: string; case_status?: string; case_dir?: string; validation_status?: string };
  mode?: "steady_state" | "transient";
  medium?: string;
  enclosure?: string;
  convection?: string;
  ambient_temperature_c?: number;
  bounding_volume_mm?: { x?: number; y?: number; z?: number };
  heat_sources?: Array<{
    id?: string;
    reference?: string;
    name?: string;
    element_id?: string;
    material_id?: string;
    surface_finish_id?: string;
    power_w?: number;
    region?: string;
    position?: ThermalPoint3;
    coordinate_frame?: ThermalCoordinateFrame;
    dimensions_mm?: { x?: number; y?: number; z?: number };
  }>;
  thermal_elements?: Array<{
    id: string;
    reference?: string;
    name?: string;
    kind?: string;
    material_id?: string;
    surface_finish_id?: string;
    enabled?: boolean;
    power_w?: number;
    position?: ThermalPoint3;
    coordinate_frame?: ThermalCoordinateFrame;
    dimensions_mm?: { x?: number; y?: number; z?: number };
    max_junction_c?: number;
    max_case_c?: number;
  }>;
  thermal_links?: Array<{
    id: string;
    from_id: string;
    to_id: string;
    kind?: string;
    enabled?: boolean;
    resistance_c_per_w?: number;
    contact_area_mm2?: number;
    thickness_mm?: number;
    material_id?: string;
  }>;
  material_library?: Array<Record<string, unknown>>;
  surface_finish_library?: Array<Record<string, unknown>>;
  thermal_screening?: Array<Record<string, unknown>>;
  flow_channels?: Array<{
    id?: string;
    path?: ThermalPoint3[];
    width_mm?: number;
    height_mm?: number;
    flow_rate_m3_s?: number;
  }>;
  fans?: ThermalFan[];
  openings?: Array<{ id?: string; face?: string; type?: string }>;
  virtual_heatsinks?: ThermalHeatsink[];
  cabinet?: { airflow_direction?: ThermalPoint3; inlet?: string; outlet?: string };
  potting?: Record<string, unknown>;
  mesh?: { cell_size_mm?: number; boundary_layers?: number; max_cells?: number };
  run?: { end_time_s?: number; write_interval_s?: number; max_iterations?: number; residual_target?: number };
  /** Completed solver result only; scenario summaries never become a displayed field. */
  field_result?: unknown;
};

export function asThermalScenario(value: Record<string, unknown> | null | undefined): ThermalScenarioView | null {
  return value ? value as ThermalScenarioView : null;
}

export function thermalVolume(scenario: ThermalScenarioView | null | undefined) {
  return {
    x: Math.max(Number(scenario?.bounding_volume_mm?.x) || 0, 1),
    y: Math.max(Number(scenario?.bounding_volume_mm?.y) || 0, 1),
    z: Math.max(Number(scenario?.bounding_volume_mm?.z) || 0, 1),
  };
}
