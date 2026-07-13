import assert from 'node:assert/strict'
import test from 'node:test'
import { createHandshake, serializeHandshake } from '../src/main/bootstrap/handshake'

test('createHandshake emits the expected runtime fields', () => {
  const handshake = createHandshake(43123, '1', '0.1.0')
  assert.equal(handshake.port, 43123)
  assert.equal(handshake.protocolVersion, '1')
  assert.equal(handshake.runtimeVersion, '0.1.0')
  assert.equal(typeof handshake.pid, 'number')
})

test('serializeHandshake returns a single JSON line without secrets', () => {
  const serialized = serializeHandshake({
    pid: 10,
    port: 43123,
    protocolVersion: '1',
    runtimeVersion: '0.1.0',
  })
  assert.equal(serialized, '{"pid":10,"port":43123,"protocolVersion":"1","runtimeVersion":"0.1.0"}')
  assert.equal(serialized.includes('token'), false)
})
