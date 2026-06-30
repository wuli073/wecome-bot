import type { RuntimeHealthPayload, RuntimeStatusPayload } from '../domain/runtime-types'
import { summarizeDisplays } from '../window/display-metrics'

export class RuntimeStateStore {
  private readonly startedAt = Date.now()
  private healthStatus: RuntimeHealthPayload['status'] = 'starting'
  private lastErrorCode: string | null = null

  constructor(
    private readonly protocolVersion: string,
    private readonly runtimeVersion: string,
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
      activeTaskCount: 0,
      lastErrorCode: this.lastErrorCode,
      displaySummary: safeDisplaySummary(),
    }
  }
}

function safeDisplaySummary() {
  try { return summarizeDisplays() } catch { return [] }
}
