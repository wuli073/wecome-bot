export function validateBboxWithinRegion(bbox: { x: number; y: number; width: number; height: number }, region: { x: number; y: number; width: number; height: number }): boolean {
  return bbox.x >= region.x && bbox.y >= region.y && bbox.x + bbox.width <= region.x + region.width && bbox.y + bbox.height <= region.y + region.height
}
