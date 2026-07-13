export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export interface WindowDescriptor {
  appType: string
  windowId: string
  ownerWindowId?: string | null
  rootWindowId?: string | null
  title: string
  executablePath: string
  processName: string
  processId: number
  displayId: string | number
  boundsLogical: Rect
  clientBounds: Rect
  scaleFactor: number
  isVisible: boolean
  isMinimized: boolean
  className?: string | null
  source?: string | null
}
