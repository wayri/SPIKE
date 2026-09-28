// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { screenThermalEnvironment, thermalEnvironmentProfiles, type ThermalEnvironmentId } from "./thermalEnvironments";

type Props = {
  boardWidthMm: number; boardHeightMm: number; ambientC: number; powerW: number;
  initialProfile?: ThermalEnvironmentId; initialAirflowM3s?: number;
  onApply: (value: { profileId: ThermalEnvironmentId; enclosure: "open" | "sealed"; convection: "natural" | "forced"; topResistanceKPerW: number; bottomResistanceKPerW: number; airflowM3s: number; assumptions: string[] }) => void;
};

export default function ThermalEnvironmentPanel({ boardWidthMm, boardHeightMm, ambientC, powerW, initialProfile = "open_air", initialAirflowM3s, onApply }: Props) {
  const [profileId, setProfileId] = useState<ThermalEnvironmentId>(initialProfile);
  const selected = thermalEnvironmentProfiles.find(profile => profile.id === profileId) ?? thermalEnvironmentProfiles[0];
  const [airflow, setAirflow] = useState(String(initialAirflowM3s ?? selected.nominalAirflowM3s));
  const screen = useMemo(() => {
    try { return { value: screenThermalEnvironment(profileId, { boardWidthMm, boardHeightMm, ambientC, powerW, airflowM3s: Number(airflow) }), error: "" }; }
    catch (error) { return { value: null, error: error instanceof Error ? error.message : "Environment inputs are invalid." }; }
  }, [airflow, ambientC, boardHeightMm, boardWidthMm, powerW, profileId]);
  const choose = (id: ThermalEnvironmentId) => {
    const profile = thermalEnvironmentProfiles.find(candidate => candidate.id === id) ?? thermalEnvironmentProfiles[0];
    setProfileId(id); setAirflow(String(profile.nominalAirflowM3s));
  };
  return <div className="wizard-section thermal-native-run thermal-environment-panel">
    <label>THERMAL ENVIRONMENT SCENARIOS</label>
    <p>Apply a reviewable first-order boundary preset, then run the object or board solver. Values are editable after application.</p>
    <div className="wizard-row"><span>Scenario</span><select aria-label="Thermal environment scenario" value={profileId} onChange={event => choose(event.target.value as ThermalEnvironmentId)}>{thermalEnvironmentProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select></div>
    {profileId === "forced_air" && <div className="wizard-row"><span>Fan airflow</span><input aria-label="Thermal scenario airflow" type="number" min="0.000001" step="0.001" value={airflow} onChange={event => setAirflow(event.target.value)} /><small>m3/s</small></div>}
    {screen.value && <div className="thermal-validation valid"><b>Approximate boundary screen</b><span>Board {screen.value.estimatedBoardTemperatureC.toFixed(1)} deg C · equivalent path {screen.value.equivalentResistanceKPerW.toFixed(2)} K/W</span>{screen.value.idealBulkAirRiseC !== null && <small>Ideal bulk-air rise {screen.value.idealBulkAirRiseC.toFixed(2)} deg C at the entered free-air flow.</small>}<small>Top {screen.value.topResistanceKPerW.toFixed(2)} K/W · bottom {screen.value.bottomResistanceKPerW.toFixed(2)} K/W · area {(screen.value.boardAreaM2 * 1e6).toFixed(0)} mm2</small>{screen.value.profile.assumptions.map(item => <small key={item}>Assumption: {item}</small>)}</div>}
    {screen.error && <div className="thermal-validation invalid"><b>Scenario cannot be applied</b><small>{screen.error}</small></div>}
    <div className="thermal-native-actions"><button className="secondary-btn" disabled={!screen.value} onClick={() => screen.value && onApply({ profileId, enclosure: screen.value.profile.enclosure, convection: screen.value.profile.convection, topResistanceKPerW: screen.value.topResistanceKPerW, bottomResistanceKPerW: screen.value.bottomResistanceKPerW, airflowM3s: Number(airflow), assumptions: screen.value.profile.assumptions })}>Apply scenario assumptions</button></div>
    <small>This screen uses prescribed heat-transfer coefficients and constant-property air. It does not resolve enclosure walls, buoyant circulation, fan curves, recirculation, component hot spots, or a spatial air field.</small>
  </div>;
}
