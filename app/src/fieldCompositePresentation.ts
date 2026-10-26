// SPDX-License-Identifier: Apache-2.0
import { admitFieldVolume, type FieldVolumeData, type FieldViewOptions } from "./fieldVolumeModel";

export type FieldComposite = { contract: "spike/field-composite-view/v1"; registration: "shared-source-coordinates"; primary: FieldVolumeData; secondary: FieldVolumeData };
/** Registration is an explicit source assertion, never inferred from matching bounds. */
export function admitFieldPresentation(value: unknown): FieldVolumeData | FieldComposite {
  const raw = value as Partial<FieldComposite> | null;
  if (raw?.contract !== "spike/field-composite-view/v1") return admitFieldVolume(value);
  if (raw.registration !== "shared-source-coordinates") throw new Error("Combined fields require explicit shared-source-coordinate registration.");
  const primary = admitFieldVolume(raw.primary), secondary = admitFieldVolume(raw.secondary);
  if (primary.lengthUnit !== secondary.lengthUnit) throw new Error("Combined fields must declare the same source coordinate units.");
  if (primary.frames.length !== secondary.frames.length || primary.frames.some((f, i) => f.timeS !== secondary.frames[i].timeS)) throw new Error("Combined fields require exactly matching saved timestamps; no time interpolation is performed.");
  if (!secondary.quantities.some(q => q.unit === "K" || q.unit === "°C")) throw new Error("Secondary solid samples require a declared temperature quantity.");
  return { contract: "spike/field-composite-view/v1", registration: raw.registration, primary, secondary };
}

export function fieldPresentationEnvelope(view: {data: FieldVolumeData; secondary?: { data: FieldVolumeData; options: FieldViewOptions }}): FieldVolumeData | FieldComposite {
  return view.secondary ? { contract: "spike/field-composite-view/v1", registration: "shared-source-coordinates", primary: view.data, secondary: view.secondary.data } : view.data;
}
