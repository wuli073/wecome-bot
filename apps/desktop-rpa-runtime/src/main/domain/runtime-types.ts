export type RuntimeHealthStatus = 'starting' | 'ready' | 'degraded' | 'stopping'

export interface RuntimeHandshake {
  pid: number
  port: number
  token: string
  protocolVersion: string
  runtimeVersion: string
}

export interface RuntimeStatusPayload {
  windowingAvailable: boolean
  captureAvailable: boolean
  inputAvailable: boolean
  providerHubReady: boolean
  sendEnabled: boolean
  allowedConnectorCount: number
  allowedConnectors: string[]
  sendErrorCode: string | null
  activeTaskCount: number
  lastErrorCode: string | null
  pasteVerification: {
    available: boolean
    reason: string | null
    providerInstanceId?: string
    diagnosticCode?: string | null
    capabilityCheckedAt?: string | null
    capabilityExpiresAt?: string | null
    capabilityAgeMs?: number | null
    capabilityProbeCount?: number
    capabilityProbeSpawnCount?: number
    lastCapabilityDiagnosticCode?: string | null
    method: string
    requiresManualConversationOpen: boolean
    supportedErrorCodes: string[]
  }
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
  broadcastSendEnabled: boolean
  allowedConnectorCount: number
  allowedConnectors: string[]
  broadcastSendErrorCode: string | null
}
