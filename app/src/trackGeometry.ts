export type TrackCapsuleDimensions = {
  centerlineLength: number;
  shapeLength: number;
  width: number;
};

/**
 * Return the rounded-stroke dimensions for a routed copper segment.
 *
 * A capsule's end-cap centers are inset by half its width. The shape must
 * therefore be one full width longer than the imported centerline so both cap
 * centers coincide with the imported endpoints. Using the centerline length as
 * the total shape length makes adjacent segments meet at only one point.
 */
export function trackCapsuleDimensions(
  centerlineLength: number,
  renderedWidth: number,
): TrackCapsuleDimensions {
  const length = Number.isFinite(centerlineLength) ? Math.max(centerlineLength, 0) : 0;
  const width = Number.isFinite(renderedWidth) ? Math.max(renderedWidth, 0) : 0;
  return {
    centerlineLength: length,
    shapeLength: Math.max(length + width, width),
    width,
  };
}

