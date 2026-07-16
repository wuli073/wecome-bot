import { app } from 'electron'
import { runRuntimeMain } from './bootstrap/runtime-entry'

const PROTOCOL_VERSION = '1'
const RUNTIME_VERSION = '0.1.1'

void runRuntimeMain({
  app,
  protocolVersion: PROTOCOL_VERSION,
  runtimeVersion: RUNTIME_VERSION,
})
