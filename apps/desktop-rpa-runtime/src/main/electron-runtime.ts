import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

export function getElectron(): any {
  const electron = require('electron')
  if (!electron || typeof electron === 'string') {
    throw new Error('ELECTRON_RUNTIME_UNAVAILABLE')
  }
  return electron
}
