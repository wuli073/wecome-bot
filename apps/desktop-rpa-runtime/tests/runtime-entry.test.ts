import assert from 'node:assert/strict'
import test from 'node:test'
import type { App, CommandLine } from 'electron'
import {
  createEphemeralRuntimeToken,
  runRuntimeMain,
} from '../src/main/bootstrap/runtime-entry'

test('createEphemeralRuntimeToken uses a non-empty 32-byte hex token for each call', () => {
  const first = createEphemeralRuntimeToken()
  const second = createEphemeralRuntimeToken()
  assert.match(first, /^[0-9a-f]{64}$/)
  assert.match(second, /^[0-9a-f]{64}$/)
  assert.notEqual(first, second)
})

test('runRuntimeMain starts without managed environment variables', async () => {
  const calls: string[] = []
  const commandLine = {
    appendSwitch: () => {
      calls.push('appendSwitch')
    },
    appendArgument: () => undefined,
    getSwitchValue: () => '',
    hasSwitch: () => false,
    removeSwitch: () => undefined,
  } as unknown as CommandLine
  const app = {
    commandLine,
    on: (() => app) as App['on'],
    whenReady: async () => {
      calls.push('whenReady')
    },
    exit: () => undefined,
  } as unknown as App

  const result = await runRuntimeMain({
    env: {},
    protocolVersion: '2',
    runtimeVersion: '0.1.0',
    ensureSingleInstance: () => {
      calls.push('lock')
    },
    bootstrapRuntimeApp: async (_app, config) => {
      calls.push(`bootstrap:${config.token}:${config.protocolVersion}:${config.runtimeVersion}`)
    },
    writeStdout: () => undefined,
    writeStderr: () => undefined,
    exit: () => undefined,
    app,
  })

  assert.equal(result.started, true)
  assert.equal(calls[0], 'lock')
  assert.equal(calls[1], 'appendSwitch')
  assert.equal(calls[2], 'whenReady')
  assert.match(calls[3], /^bootstrap:[0-9a-f]{64}:2:0\.1\.0$/)
})

test('runRuntimeMain acquires the single-instance lock and bootstraps with an ephemeral token', async () => {
  const calls: string[] = []
  const commandLine = {
    appendSwitch: () => {
      calls.push('appendSwitch')
    },
    appendArgument: () => undefined,
    getSwitchValue: () => '',
    hasSwitch: () => false,
    removeSwitch: () => undefined,
  } as unknown as CommandLine
  const app = {
    commandLine,
    on: ((eventName) => {
      calls.push(`on:${eventName}`)
      return app
    }) as App['on'],
    whenReady: async () => {
      calls.push('whenReady')
    },
    exit: () => undefined,
  } as unknown as App

  const result = await runRuntimeMain({
    env: {},
    protocolVersion: '2',
    runtimeVersion: '0.1.0',
    ensureSingleInstance: () => {
      calls.push('lock')
    },
    bootstrapRuntimeApp: async (_app, config) => {
      calls.push(`bootstrap:${config.token}:${config.protocolVersion}:${config.runtimeVersion}`)
    },
    writeStdout: () => undefined,
    writeStderr: () => undefined,
    exit: () => undefined,
    app,
  })

  assert.equal(result.started, true)
  assert.deepEqual(calls.slice(0, 4), [
    'lock',
    'appendSwitch',
    'on:window-all-closed',
    'whenReady',
  ])
  assert.match(calls[4], /^bootstrap:[0-9a-f]{64}:2:0\.1\.0$/)
})

test('runRuntimeMain forwards unrestricted broadcast send configuration to bootstrap', async () => {
  let capturedConfig: Record<string, unknown> = {}
  const commandLine = {
    appendSwitch: () => undefined,
    appendArgument: () => undefined,
    getSwitchValue: () => '',
    hasSwitch: () => false,
    removeSwitch: () => undefined,
  } as unknown as CommandLine
  const app = {
    commandLine,
    on: (() => app) as App['on'],
    whenReady: async () => undefined,
    exit: () => undefined,
  } as unknown as App

  const result = await runRuntimeMain({
    env: {
      LANGBOT_BROADCAST_SEND_ENABLED: '1',
      LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS: ' wxwork-local , , wxwork-local ',
    },
    protocolVersion: '2',
    runtimeVersion: '0.1.0',
    ensureSingleInstance: () => undefined,
    bootstrapRuntimeApp: async (_app, config) => {
      capturedConfig = config as unknown as Record<string, unknown>
    },
    writeStdout: () => undefined,
    writeStderr: () => undefined,
    exit: () => undefined,
    app,
  })

  assert.equal(result.started, true)
  assert.match(String(capturedConfig.token), /^[0-9a-f]{64}$/)
  assert.deepEqual({ ...capturedConfig, token: '<ephemeral>' }, {
    token: '<ephemeral>',
    protocolVersion: '2',
    runtimeVersion: '0.1.0',
    broadcastSendEnabled: true,
    allowedConnectorCount: 0,
    allowedConnectors: ['*'],
    broadcastSendErrorCode: null,
  })
})
