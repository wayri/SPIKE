// SPDX-License-Identifier: Apache-2.0
import { createElement, forwardRef, type SVGProps } from "react";
import type { LucideIcon, LucideProps } from "./icons";

type Face = "top" | "bottom" | "front" | "back" | "left" | "right" | "iso";

const faces: Record<Face, string> = {
  top: "M12 3 21 8 12 13 3 8Z",
  bottom: "M3 16 12 21 21 16 12 11Z",
  front: "M12 13 21 8 21 18 12 23Z",
  back: "M3 8 12 13 12 23 3 18Z",
  left: "M3 8 12 13 12 23 3 18Z",
  right: "M12 13 21 8 21 18 12 23Z",
  iso: "M12 3 21 8 12 13 3 8Z M12 13 21 8 21 18 12 23Z",
};

function cameraViewIcon(name: string, face: Face): LucideIcon {
  const Icon = forwardRef<SVGSVGElement, LucideProps>(({ color = "currentColor", size = 24, strokeWidth = 1.8, absoluteStrokeWidth, children, ...props }, ref) => {
    const label = props["aria-label"];
    const resolvedStroke = absoluteStrokeWidth && typeof size === "number" ? Number(strokeWidth) * 24 / size : strokeWidth;
    const accessibility: SVGProps<SVGSVGElement> = label || props["aria-labelledby"] ? { role: "img" } : { "aria-hidden": true };
    return <svg ref={ref} xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 26" fill="none" stroke={color} strokeWidth={resolvedStroke} strokeLinecap="round" strokeLinejoin="round" {...accessibility} {...props}>
      {label ? <title>{String(label)}</title> : null}
      {createElement("path", { d: faces[face], fill: "currentColor", opacity: .28, stroke: "none" })}
      <path d="M12 3 21 8 12 13 3 8 12 3ZM3 8v10l9 5 9-5V8M12 13v10"/>
      {face === "back" && <path d="M4.5 7.2 12 11.4" strokeDasharray="1.6 1.6"/>}
      {face === "left" && <path d="M4.2 10v6" strokeWidth={Number(resolvedStroke) + .7}/>} 
      {face === "right" && <path d="M19.8 10v6" strokeWidth={Number(resolvedStroke) + .7}/>} 
      {children}
    </svg>;
  }) as LucideIcon;
  Icon.displayName = name;
  return Icon;
}

export const CameraTopIcon = cameraViewIcon("CameraTopIcon", "top");
export const CameraBottomIcon = cameraViewIcon("CameraBottomIcon", "bottom");
export const CameraFrontIcon = cameraViewIcon("CameraFrontIcon", "front");
export const CameraBackIcon = cameraViewIcon("CameraBackIcon", "back");
export const CameraLeftIcon = cameraViewIcon("CameraLeftIcon", "left");
export const CameraRightIcon = cameraViewIcon("CameraRightIcon", "right");
export const CameraIsometricIcon = cameraViewIcon("CameraIsometricIcon", "iso");
