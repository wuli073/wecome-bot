import { app } from 'electron'
import { bootstrapRuntimeApp } from './bootstrap/runtime-app'
import { ensureSingleInstance } from './bootstrap/single-instance'

const PROTOCOL_VERSION = '1'
const RUNTIME_VERSION = '0.1.0'

function readToken(): string {
  const token = process.env.LANGBOT_RPA_TOKEN ?? ''
  if (!token) {
    throw new Error('LANGBOT_RPA_TOKEN is required')
  }
  return token
}

ensureSingleInstance()
app.commandLine.appendSwitch('disable-http-cache')
app.on('window-all-closed', () => {
  // Keep the headless runtime alive until its parent process stops it.
})

void app.whenReady().then(async () => {
  try {
    await bootstrapRuntimeApp(app, {
      token: readToken(),
      protocolVersion: PROTOCOL_VERSION,
      runtimeVersion: RUNTIME_VERSION,
    })
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`)
    app.exit(1)
  }
})
