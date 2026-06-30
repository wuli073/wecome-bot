export function isTrustedLayoutDetection(result: { confidence?: number }): boolean { return (result.confidence ?? 0) >= 0.8 }
