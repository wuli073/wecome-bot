export function hasRedDotPixel(pixels: Array<{ r: number; g: number; b: number; a?: number }>): boolean {
  return pixels.some((pixel) => pixel.r > 180 && pixel.g < 90 && pixel.b < 90 && (pixel.a ?? 255) > 120)
}
