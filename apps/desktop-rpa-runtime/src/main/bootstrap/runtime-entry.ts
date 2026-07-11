import type { App } from 'electron'
import { bootstrapRuntimeApp } from './runtime-app'
import { ensureSingleInstance } from './single-instance'
import type { RuntimeBootstrapConfig } from '../domain/runtime-types'

export const MANAGED_START_REQUIRED_ERROR_CODE = 'RUNTIME_MANAGED_START_REQUIRED'

type RuntimeEnvironment = Record<string, string | undefined>

type RuntimeEntryApp = Pick<App, 'commandLine' | 'on' | 'whenReady' | 'exit'>

type RuntimeEntryDependencies = {
  app: RuntimeEntryApp
  env?: RuntimeEnvironment
  protocolVersion: string
  runtimeVersion: string
  ensureSingleInstance?: () => void
  bootstrapRuntimeApp?: (app: App, config: RuntimeBootstrapConfig) => Promise<void>
  writeStdout?: (text: string) => void
  writeStderr?: (text: string) => void
  exit?: (code: number) => void
}

function normalizeAllowedConnectors(rawValue: string | undefined): string[] {
  const normalized: string[] = []
  const seen = new Set<string>()
  for (const rawItem of String(rawValue ?? '').split(',')) {
    const connectorId = rawItem.trim()
    if (!connectorId || seen.has(connectorId)) continue
    seen.add(connectorId)
    normalized.push(connectorId)
  }
  return normalized
}

export function resolveBroadcastSendBootstrapConfig(env: RuntimeEnvironment) {
  const requestedEnabled = String(env.LANGBOT_BROADCAST_SEND_ENABLED ?? '').trim() === '1'
  const allowedConnectors = normalizeAllowedConnectors(env.LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS)
  const broadcastSendEnabled = requestedEnabled && allowedConnectors.length > 0
  return {
    broadcastSendEnabled,
    allowedConnectorCount: allowedConnectors.length,
    allowedConnectors,
    broadcastSendErrorCode: requestedEnabled && allowedConnectors.length === 0
      ? 'BROADCAST_SEND_ALLOWLIST_REQUIRED'
      : null,
  }
}

export type ManagedRuntimeEnvironmentValidationResult =
  | {
    ok: true
    token: string
  }
  | {
    ok: false
    errorCode: typeof MANAGED_START_REQUIRED_ERROR_CODE
  }

export function validateManagedRuntimeEnvironment(
  env: RuntimeEnvironment,
): ManagedRuntimeEnvironmentValidationResult {
  const managed = String(env.LANGBOT_RPA_MANAGED ?? '').trim()
  const token = String(env.LANGBOT_RPA_TOKEN ?? '').trim()
  if (managed !== '1' || !token) {
    return {
      ok: false,
      errorCode: MANAGED_START_REQUIRED_ERROR_CODE,
    }
  }
  return {
    ok: true,
    token,
  }
}

export async function runRuntimeMain(
  dependencies: RuntimeEntryDependencies,
): Promise<{ started: boolean; errorCode?: string }> {
  const env = dependencies.env ?? (process.env as RuntimeEnvironment)
  const validation = validateManagedRuntimeEnvironment(env)
  const writeStderr = dependencies.writeStderr ?? ((text: string) => {
    process.stderr.write(text)
  })
  const exit = dependencies.exit ?? ((code: number) => {
    dependencies.app.exit(code)
  })

  if (!validation.ok) {
    writeStderr(`${validation.errorCode}\n`)
    exit(1)
    return {
      started: false,
      errorCode: validation.errorCode,
    }
  }

  const ensureLock = dependencies.ensureSingleInstance ?? (() => {
    ensureSingleInstance()
  })
  const bootstrap = dependencies.bootstrapRuntimeApp ?? (async (app, config) => {
    await bootstrapRuntimeApp(app, config)
  })

  ensureLock()
  dependencies.app.commandLine.appendSwitch('disable-http-cache')
  dependencies.app.on('window-all-closed', () => {
    // Keep the headless runtime alive until its parent process stops it.
  })

  try {
    await dependencies.app.whenReady()
    const broadcastSendConfig = resolveBroadcastSendBootstrapConfig(env)
    await bootstrap(dependencies.app as App, {
      token: validation.token,
      protocolVersion: dependencies.protocolVersion,
      runtimeVersion: dependencies.runtimeVersion,
      ...broadcastSendConfig,
    })
    return { started: true }
  } catch (error) {
    writeStderr(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`)
    exit(1)
    return {
      started: false,
      errorCode: 'RUNTIME_START_FAILED',
    }
  }
}
