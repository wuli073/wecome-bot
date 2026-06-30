import type { RuntimeHandshake } from '../domain/runtime-types'

export function createHandshake(port: number, protocolVersion: string, runtimeVersion: string): RuntimeHandshake {
  return {
    pid: process.pid,
    port,
    protocolVersion,
    runtimeVersion,
  }
}

export function serializeHandshake(handshake: RuntimeHandshake): string {
  return JSON.stringify(handshake)
}
