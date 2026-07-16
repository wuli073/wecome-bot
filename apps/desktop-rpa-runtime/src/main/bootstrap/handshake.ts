import type { RuntimeHandshake } from '../domain/runtime-types'

export function createHandshake(port: number, token: string, protocolVersion: string, runtimeVersion: string): RuntimeHandshake {
  return {
    pid: process.pid,
    port,
    token,
    protocolVersion,
    runtimeVersion,
  }
}

export function serializeHandshake(handshake: RuntimeHandshake): string {
  return JSON.stringify(handshake)
}
