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

test('runtime status returns broadcast send diagnostics without enabling auto-send', async () => {
  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0', {
      broadcastSendEnabled: true,
      allowedConnectorCount: 1,
      allowedConnectors: ['wxwork-local'],
      broadcastSendErrorCode: null,
    }),
    runtimeHost: new RuntimeHost(),
  })
  try {
    const response = await request(server.port, 'GET', '/v1/runtime/status')
    assert.equal(response.statusCode, 200)
    assert.equal(response.payload.sendEnabled, true)
    assert.equal(response.payload.allowedConnectorCount, 1)
    assert.deepEqual(response.payload.allowedConnectors, ['wxwork-local'])
    assert.equal(response.payload.sendErrorCode, null)
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

test('runtime POST creates a task envelope immediately and GET returns the final result later', async () => {
  const controls: { releaseTask?: () => void } = {}
  const runtimeHost = new RuntimeHost()
  runtimeHost.runner.run = (async () => {
    await new Promise<void>((resolve) => { controls.releaseTask = () => resolve() })
    return { status: 'succeeded', stage: 'completed', draftWritten: true }
  }) as never

  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost,
  })
  try {
    const created = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'async-1',
      requestDigest: 'digest-async-1',
      conversationName: 'Customer A',
      draftText: 'hello',
    })
    assert.equal(created.statusCode, 200)
    assert.equal(created.payload.status, 'running')
    assert.equal(created.payload.requestDigest, 'digest-async-1')
    assert.equal(created.payload.result, undefined)

    controls.releaseTask?.()
    await new Promise((resolve) => setTimeout(resolve, 20))
    const polled = await request(server.port, 'GET', `/v1/tasks/${created.payload.id}`)
    assert.equal(polled.statusCode, 200)
    assert.equal(polled.payload.status, 'succeeded')
    assert.equal((polled.payload.result as Record<string, unknown>).draftWritten, true)
  } finally {
    controls.releaseTask?.()
    await server.close()
  }
})

test('runtime returns idempotency conflict when the same key is reused with a different request digest', async () => {
  const runtimeHost = new RuntimeHost()
  runtimeHost.runner.run = (async () => ({ status: 'succeeded', stage: 'completed' })) as never
  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost,
  })
  try {
    const created = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'conflict-1',
      requestDigest: 'digest-a',
      conversationName: 'Customer A',
      draftText: 'hello',
    })
    assert.equal(created.statusCode, 200)

    const conflicted = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'conflict-1',
      requestDigest: 'digest-b',
      conversationName: 'Customer A',
      draftText: 'hello',
    })
    assert.equal(conflicted.statusCode, 409)
    assert.equal(conflicted.payload.errorCode, 'IDEMPOTENCY_KEY_CONFLICT')
  } finally {
    await server.close()
  }
})

test('runtime returns idempotency conflict when the same key is reused with a different action', async () => {
  const runtimeHost = new RuntimeHost()
  runtimeHost.runner.run = (async () => ({ status: 'succeeded', stage: 'completed' })) as never
  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost,
  })
  try {
    const created = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'conflict-2',
      requestDigest: 'digest-a',
      conversationName: 'Customer A',
      draftText: 'hello',
    })
    assert.equal(created.statusCode, 200)

    const conflicted = await request(server.port, 'POST', '/v1/tasks/send-message', {
      action: 'send_message',
      idempotencyKey: 'conflict-2',
      requestDigest: 'digest-a',
      conversationName: 'Customer A',
      messageText: 'hello',
    })
    assert.equal(conflicted.statusCode, 409)
    assert.equal(conflicted.payload.errorCode, 'IDEMPOTENCY_KEY_CONFLICT')
  } finally {
    await server.close()
  }
})

test('server close rejects concurrent task POSTs with 503 and no task residue', async () => {
  const controls: { releaseTask?: () => void; releaseCreate?: () => void } = {}
  const runtimeHost = new RuntimeHost()
  runtimeHost.runner.run = (async () => {
    await new Promise<void>((resolve) => { controls.releaseTask = () => resolve() })
    return { status: 'succeeded', stage: 'completed' }
  }) as never
  const originalCreateTask = runtimeHost.createTask.bind(runtimeHost)
  let createTaskCallCount = 0
  runtimeHost.createTask = (async (...args) => {
    createTaskCallCount += 1
    if (createTaskCallCount > 1) {
      await new Promise<void>((resolve) => { controls.releaseCreate = () => resolve() })
    }
    return originalCreateTask(...args)
  }) as typeof runtimeHost.createTask

  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost,
  })

  try {
    const created = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'close-inflight',
      requestDigest: 'close-inflight-digest',
      conversationName: 'Customer A',
      draftText: 'hello',
    })
    assert.equal(created.statusCode, 200)

    const rejectedPromise = request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'close-rejected',
      requestDigest: 'close-rejected-digest',
      conversationName: 'Customer A',
      draftText: 'hello',
    })
    await new Promise((resolve) => setTimeout(resolve, 10))
    const closePromise = server.close()
    controls.releaseCreate?.()
    const rejected = await rejectedPromise

    assert.equal(rejected.statusCode, 503)
    assert.equal(rejected.payload.errorCode, 'RUNTIME_SHUTTING_DOWN')
    assert.equal('id' in rejected.payload, false)
    assert.equal(runtimeHost.registry.all().some((task) => task.idempotencyKey === 'close-rejected'), false)

    controls.releaseTask?.()
    await closePromise
  } finally {
    controls.releaseTask?.()
  }
})
