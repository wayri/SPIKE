// SPDX-License-Identifier: Apache-2.0

export type ThermalEnvironmentId = "open_air" | "closed_box" | "forced_air";

export type ThermalEnvironmentProfile = {
  id: ThermalEnvironmentId;
  name: string;
  enclosure: "open" | "sealed";
  convection: "natural" | "forced";
  topHeatTransferCoefficientWm2K: number;
  bottomHeatTransferCoefficientWm2K: number;
  nominalAirflowM3s: number;
  assumptions: string[];
};

export type ThermalEnvironmentScreen = {
  profile: ThermalEnvironmentProfile;
  boardAreaM2: number;
  topResistanceKPerW: number;
  bottomResistanceKPerW: number;
  equivalentResistanceKPerW: number;
  estimatedBoardTemperatureC: number;
  idealBulkAirRiseC: number | null;
  modelStatus: "approximate";
};

export const thermalEnvironmentProfiles: readonly ThermalEnvironmentProfile[] = [
  {
    id: "open_air", name: "Board in still air", enclosure: "open", convection: "natural",
    topHeatTransferCoefficientWm2K: 8, bottomHeatTransferCoefficientWm2K: 5, nominalAirflowM3s: 0,
    assumptions: ["Horizontal board in room-temperature air", "Unobstructed board faces", "Natural convection and surface radiation are combined into prescribed effective coefficients"],
  },
  {
    id: "closed_box", name: "Board in closed box", enclosure: "sealed", convection: "natural",
    topHeatTransferCoefficientWm2K: 3, bottomHeatTransferCoefficientWm2K: 2, nominalAirflowM3s: 0,
    assumptions: ["Sealed stagnant-air enclosure", "No ventilation or fan flow", "Box walls and internal air are not resolved; coefficients represent a conservative internal path only"],
  },
  {
    id: "forced_air", name: "Board under forced air", enclosure: "open", convection: "forced",
    topHeatTransferCoefficientWm2K: 35, bottomHeatTransferCoefficientWm2K: 20, nominalAirflowM3s: 0.012,
    assumptions: ["Uniform fan flow parallel to the board", "Both board faces remain exposed", "Fan free-air flow is prescribed; pressure loss, bypass, recirculation, and local velocity are not solved"],
  },
] as const;

const finitePositive = (value: number, name: string) => {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${name} must be positive and finite.`);
  return value;
};

export function screenThermalEnvironment(
  id: ThermalEnvironmentId,
  input: { boardWidthMm: number; boardHeightMm: number; ambientC: number; powerW: number; airflowM3s?: number },
): ThermalEnvironmentScreen {
  const profile = thermalEnvironmentProfiles.find(candidate => candidate.id === id);
  if (!profile) throw new Error(`Unknown thermal environment: ${id}`);
  const area = finitePositive(input.boardWidthMm, "Board width") * finitePositive(input.boardHeightMm, "Board height") * 1e-6;
  if (!Number.isFinite(input.powerW) || input.powerW < 0) throw new Error("Board power must be finite and non-negative.");
  const power = input.powerW;
  if (!Number.isFinite(input.ambientC) || input.ambientC < -273.15) throw new Error("Ambient temperature is invalid.");
  const topResistance = 1 / (profile.topHeatTransferCoefficientWm2K * area);
  const bottomResistance = 1 / (profile.bottomHeatTransferCoefficientWm2K * area);
  const equivalent = 1 / (1 / topResistance + 1 / bottomResistance);
  const flow = input.airflowM3s ?? profile.nominalAirflowM3s;
  if (!Number.isFinite(flow) || flow < 0) throw new Error("Airflow must be finite and non-negative.");
  // Constant-property standard air screen: rho=1.204 kg/m3, cp=1005 J/(kg K).
  const airRise = id === "forced_air" && flow > 0 ? power / (1.204 * 1005 * flow) : null;
  return {
    profile, boardAreaM2: area, topResistanceKPerW: topResistance, bottomResistanceKPerW: bottomResistance,
    equivalentResistanceKPerW: equivalent, estimatedBoardTemperatureC: input.ambientC + power * equivalent,
    idealBulkAirRiseC: airRise, modelStatus: "approximate",
  };
}
