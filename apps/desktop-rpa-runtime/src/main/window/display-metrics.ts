import { getElectron } from '../electron-runtime'

export interface DisplaySummary { id: string | number; scaleFactor: number; bounds: { x: number; y: number; width: number; height: number }; workArea: { x: number; y: number; width: number; height: number } }

export function summarizeDisplays(displays?: Array<{ id: string | number; scaleFactor: number; bounds: { x: number; y: number; width: number; height: number }; workArea: { x: number; y: number; width: number; height: number } }>): DisplaySummary[] {
  const source = displays ?? getElectron().screen.getAllDisplays()
  return source.map((display: { id: string | number; scaleFactor: number; bounds: { x: number; y: number; width: number; height: number }; workArea: { x: number; y: number; width: number; height: number } }) => ({
    id: display.id,
    scaleFactor: display.scaleFactor,
    bounds: { ...display.bounds },
    workArea: { ...display.workArea },
  }))
}

export function displayForRect(rect: { x: number; y: number; width: number; height: number }) {
  const display = getElectron().screen.getDisplayMatching(rect)
  return { id: display.id, scaleFactor: display.scaleFactor, bounds: { ...display.bounds }, workArea: { ...display.workArea } }
}
