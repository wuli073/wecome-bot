export function logicalToPhysicalRect(rect: { x: number; y: number; width: number; height: number }, scaleFactor: number) {
  return { x: Math.round(rect.x * scaleFactor), y: Math.round(rect.y * scaleFactor), width: Math.round(rect.width * scaleFactor), height: Math.round(rect.height * scaleFactor) }
}

export function physicalToLogicalRect(rect: { x: number; y: number; width: number; height: number }, scaleFactor: number) {
  return { x: rect.x / scaleFactor, y: rect.y / scaleFactor, width: rect.width / scaleFactor, height: rect.height / scaleFactor }
}
