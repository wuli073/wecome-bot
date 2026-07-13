import assert from 'node:assert/strict'
import test from 'node:test'
import type { App, CommandLine } from 'electron'
import {
  MANAGED_START_REQUIRED_ERROR_CODE,
  validateManagedRuntimeEnvironment,
  runRuntimeMain,
} from '../src/main/bootstrap/runtime-entry'

test('validateManagedRuntimeEnvironment rejects missing managed marker', () => {
  const result = validateManagedRuntimeEnvironment({})
  assert.equal(result.ok, false)
  assert.equal(result.errorCode, MANAGED_START_REQUIRED_ERROR_CODE)
})

test('validateManagedRuntimeEnvironment rejects invalid managed marker', () => {
  const result = validateManagedRuntimeEnvironment({
    LANGBOT_RPA_MANAGED: '0',
    LANGBOT_RPA_TOKEN: 'secret-token',
  })
  assert.equal(result.ok, false)
  assert.equal(result.errorCode, MANAGED_START_REQUIRED_ERROR_CODE)
})

test('validateManagedRuntimeEnvironment rejects missing token', () => {
  const result = validateManagedRuntimeEnvironment({
    LANGBOT_RPA_MANAGED: '1',
  })
  assert.equal(result.ok, false)
  assert.equal(result.errorCode, MANAGED_START_REQUIRED_ERROR_CODE)
})

test('runRuntimeMain exits before acquiring the single-instance lock when startup is unmanaged', async () => {
  let ensureSingleInstanceCalled = false
  let whenReadyCalled = false
  let appendSwitchCalled = false
  let bootstrapCalled = false
  const stderrWrites: string[] = []
  const exitCodes: number[] = []
  const commandLine = {
    appendSwitch: () => {
      appendSwitchCalled = true
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
      whenReadyCalled = true
    },
    exit: () => undefined,
  } as unknown as App

  const result = await runRuntimeMain({
    env: {},
    protocolVersion: '1',
    runtimeVersion: '0.1.0',
    ensureSingleInstance: () => {
      ensureSingleInstanceCalled = true
    },
    bootstrapRuntimeApp: async () => {
      bootstrapCalled = true
    },
    writeStdout: () => {
      throw new Error('stdout should not be written for unmanaged startup')
    },
    writeStderr: (text) => {
      stderrWrites.push(text)
    },
    exit: (code) => {
      exitCodes.push(code)
    },
    app,
  })

  assert.equal(result.started, false)
  assert.equal(ensureSingleInstanceCalled, false)
  assert.equal(whenReadyCalled, false)
  assert.equal(appendSwitchCalled, false)
  assert.equal(bootstrapCalled, false)
  assert.deepEqual(stderrWrites, [`${MANAGED_START_REQUIRED_ERROR_CODE}\n`])
  assert.deepEqual(exitCodes, [1])
})

test('runRuntimeMain acquires the single-instance lock and bootstraps only for managed startup', async () => {
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
    env: {
      LANGBOT_RPA_MANAGED: '1',
      LANGBOT_RPA_TOKEN: 'secret-token',
    },
    protocolVersion: '1',
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
  assert.deepEqual(calls, [
    'lock',
    'appendSwitch',
    'on:window-all-closed',
    'whenReady',
    'bootstrap:secret-token:1:0.1.0',
  ])
})

test('runRuntimeMain forwards normalized broadcast send configuration to bootstrap', async () => {
  let capturedConfig: Record<string, unknown> | null = null
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
      LANGBOT_RPA_MANAGED: '1',
      LANGBOT_RPA_TOKEN: 'secret-token',
      LANGBOT_BROADCAST_SEND_ENABLED: '1',
      LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS: ' wxwork-local , , wxwork-local ',
    },
    protocolVersion: '1',
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
  assert.deepEqual(capturedConfig, {
    token: 'secret-token',
    protocolVersion: '1',
    runtimeVersion: '0.1.0',
    broadcastSendEnabled: true,
    allowedConnectorCount: 1,
    allowedConnectors: ['wxwork-local'],
    broadcastSendErrorCode: null,
  })
})
