import type { App } from 'electron'
import { createHandshake, serializeHandshake } from './handshake'
import { createLocalHttpServer } from '../api/local-http-server'
import { RuntimeStateStore } from '../runtime/state-store'
import type { RuntimeBootstrapConfig } from '../domain/runtime-types'

export async function bootstrapRuntimeApp(_app: App, config: RuntimeBootstrapConfig): Promise<void> {
  const stateStore = new RuntimeStateStore(config.protocolVersion, config.runtimeVersion)
  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: config.token,
    stateStore,
  })
  stateStore.markReady()
  process.stdout.write(`${serializeHandshake(createHandshake(server.port, config.protocolVersion, config.runtimeVersion))}\n`)

  const shutdown = async () => {
    stateStore.markStopping()
    await server.close()
  }

  process.once('SIGTERM', () => {
    void shutdown().finally(() => process.exit(0))
  })
  process.once('SIGINT', () => {
    void shutdown().finally(() => process.exit(0))
  })
}
