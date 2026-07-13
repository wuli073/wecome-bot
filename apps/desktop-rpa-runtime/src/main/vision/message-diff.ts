export function comparePixelBuffers(left: Uint8Array, right: Uint8Array): { changed: boolean; changedPixels: number } {
  const length = Math.min(left.length, right.length)
  let changedPixels = 0
  for (let index = 0; index < length; index += 1) {
    if (left[index] !== right[index]) changedPixels += 1
  }
  return { changed: changedPixels > 0 || left.length !== right.length, changedPixels: changedPixels + Math.abs(left.length - right.length) }
}
