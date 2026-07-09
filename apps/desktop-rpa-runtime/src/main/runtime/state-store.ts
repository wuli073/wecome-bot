import type { RuntimeHealthPayload, RuntimeStatusPayload } from '../domain/runtime-types'
import { summarizeDisplays } from '../window/display-metrics'

type BroadcastSendState = {
  broadcastSendEnabled: boolean
  allowedConnectorCount: number
  allowedConnectors: string[]
  broadcastSendErrorCode: string | null
}

export class RuntimeStateStore {
  private readonly startedAt = Date.now()
  private healthStatus: RuntimeHealthPayload['status'] = 'starting'
  private lastErrorCode: string | null = null

  constructor(
    private readonly protocolVersion: string,
    private readonly runtimeVersion: string,
    private readonly broadcastSendState: BroadcastSendState = {
      broadcastSendEnabled: false,
      allowedConnectorCount: 0,
      allowedConnectors: [],
      broadcastSendErrorCode: null,
    },
  ) {}

  markReady(): void {
    this.healthStatus = 'ready'
  }

  markStopping(): void {
    this.healthStatus = 'stopping'
  }

  markDegraded(errorCode: string): void {
    this.healthStatus = 'degraded'
    this.lastErrorCode = errorCode
  }

  getHealth(): RuntimeHealthPayload {
    return {
      status: this.healthStatus,
      protocolVersion: this.protocolVersion,
      runtimeVersion: this.runtimeVersion,
      uptimeMs: Date.now() - this.startedAt,
    }
  }

  getStatus(): RuntimeStatusPayload {
    return {
      windowingAvailable: true,
      captureAvailable: true,
      inputAvailable: true,
      providerHubReady: true,
      sendEnabled: this.broadcastSendState.broadcastSendEnabled,
      allowedConnectorCount: this.broadcastSendState.allowedConnectorCount,
      allowedConnectors: [...this.broadcastSendState.allowedConnectors],
      sendErrorCode: this.broadcastSendState.broadcastSendErrorCode,
      activeTaskCount: 0,
      lastErrorCode: this.lastErrorCode,
      pasteVerification: {
        available: false,
        reason: 'PASTE_VERIFICATION_DISABLED',
        diagnosticCode: null,
        capabilityCheckedAt: null,
        capabilityExpiresAt: null,
        capabilityAgeMs: null,
        capabilityProbeCount: 0,
        capabilityProbeSpawnCount: 0,
        lastCapabilityDiagnosticCode: null,
        method: 'unavailable',
        requiresManualConversationOpen: false,
        supportedErrorCodes: [],
      },
      displaySummary: safeDisplaySummary(),
    }
  }
}

function safeDisplaySummary() {
  try { return summarizeDisplays() } catch { return [] }
}
