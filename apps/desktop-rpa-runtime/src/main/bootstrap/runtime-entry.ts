import type { App } from 'electron'
import { randomBytes } from 'node:crypto'
import { bootstrapRuntimeApp } from './runtime-app'
import { ensureSingleInstance } from './single-instance'
import type { RuntimeBootstrapConfig } from '../domain/runtime-types'

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

export function resolveBroadcastSendBootstrapConfig(env: RuntimeEnvironment) {
  void env
  return {
    broadcastSendEnabled: true,
    allowedConnectorCount: 0,
    allowedConnectors: ['*'],
    broadcastSendErrorCode: null,
  }
}

export function createEphemeralRuntimeToken(): string {
  return randomBytes(32).toString('hex')
}

export async function runRuntimeMain(
  dependencies: RuntimeEntryDependencies,
): Promise<{ started: boolean; errorCode?: string }> {
  const env = dependencies.env ?? (process.env as RuntimeEnvironment)
  const writeStderr = dependencies.writeStderr ?? ((text: string) => {
    process.stderr.write(text)
  })
  const exit = dependencies.exit ?? ((code: number) => {
    dependencies.app.exit(code)
  })

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
      token: createEphemeralRuntimeToken(),
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
