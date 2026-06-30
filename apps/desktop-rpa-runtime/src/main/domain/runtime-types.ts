export type RuntimeHealthStatus = 'starting' | 'ready' | 'degraded' | 'stopping'

export interface RuntimeHandshake {
  pid: number
  port: number
  protocolVersion: string
  runtimeVersion: string
}

export interface RuntimeStatusPayload {
  windowingAvailable: boolean
  captureAvailable: boolean
  inputAvailable: boolean
  providerHubReady: boolean
  activeTaskCount: number
  lastErrorCode: string | null
  displaySummary: Array<{
    id: string | number
    scaleFactor: number
    bounds: { x: number; y: number; width: number; height: number }
    workArea?: { x: number; y: number; width: number; height: number }
  }>
}

export interface RuntimeHealthPayload {
  status: RuntimeHealthStatus
  protocolVersion: string
  runtimeVersion: string
  uptimeMs: number
}

export interface RuntimeBootstrapConfig {
  token: string
  protocolVersion: string
  runtimeVersion: string
}
