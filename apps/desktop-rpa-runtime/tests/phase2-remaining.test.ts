import assert from 'node:assert/strict'
import test from 'node:test'
import http from 'node:http'
import { createLocalHttpServer } from '../src/main/api/local-http-server'
import { RuntimeStateStore } from '../src/main/runtime/state-store'
import { RuntimeHost } from '../src/main/runtime/runtime-host'

function request(port: number, method: string, path: string, body?: Record<string, unknown>) {
  return new Promise<{ statusCode: number; payload: Record<string, unknown> }>((resolve, reject) => {
    const req = http.request({
      host: '127.0.0.1',
      port,
      method,
      path,
      headers: {
        Authorization: 'Bearer token',
        'Content-Type': 'application/json',
      },
    }, (res) => {
      const chunks: Buffer[] = []
      res.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode ?? 0,
          payload: JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'),
        })
      })
    })
    req.on('error', reject)
    if (body) req.write(JSON.stringify(body))
    req.end()
  })
}

test('runtime calibration and context-confirmation routes are removed', async () => {
  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost: new RuntimeHost(),
  })
  try {
    assert.equal((await request(server.port, 'POST', '/v1/calibration-sessions', {})).statusCode, 404)
    assert.equal((await request(server.port, 'GET', '/v1/calibration-sessions/cal-1')).statusCode, 404)
    assert.equal((await request(server.port, 'POST', '/v1/calibration-sessions/cal-1/cancel', {})).statusCode, 404)
    assert.equal((await request(server.port, 'POST', '/v1/tasks/context-confirmations/prepare', {})).statusCode, 404)
  } finally {
    await server.close()
  }
})

test('runtime paste-draft rejects forbidden calibration and confirmation fields', async () => {
  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost: new RuntimeHost(),
  })
  try {
    for (const key of ['profile', 'windowBinding', 'windowKey', 'regionProfile', 'calibrationSessionId', 'humanConfirmationToken', 'targetConversation']) {
      const response = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
        action: 'paste_draft',
        idempotencyKey: `idem-${key}`,
        requestDigest: `digest-${key}`,
        conversationName: 'Customer A',
        draftText: 'hello',
        [key]: {},
      })
      assert.equal(response.statusCode, 400)
      assert.equal(response.payload.errorCode, 'UNEXPECTED_REQUEST_FIELD')
    }
  } finally {
    await server.close()
  }
})
