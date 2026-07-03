import assert from 'node:assert/strict'
import test from 'node:test'
import { runSendMessageTask } from '../src/main/input/send-controller'

class RecordingInputDriver {
  readonly events: Array<{ type: string; payload: unknown }> = []
  async click(point: { x: number; y: number }): Promise<void> { this.events.push({ type: 'click', payload: point }) }
  async hotkey(keys: string[]): Promise<void> { this.events.push({ type: 'hotkey', payload: keys }) }
  async typeText(text: string): Promise<void> { this.events.push({ type: 'typeText', payload: text }) }
}

test('send-message requires confirmation token', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_message',
    idempotencyKey: 'idem-1',
    requestDigest: 'digest-1',
    messageText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
  })

  assert.equal(result.status, 'blocked')
  assert.equal(result.errorCode, 'CONFIRMATION_TOKEN_REQUIRED')
  assert.equal(input.events.length, 0)
})

test('send-message remains blocked when force-disable-send is enabled', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_message',
    idempotencyKey: 'idem-2',
    requestDigest: 'digest-2',
    messageText: 'hello',
    confirmationToken: 'confirm-1',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: true,
  })

  assert.equal(result.status, 'blocked')
  assert.equal(result.errorCode, 'SEND_DRIVER_DISABLED')
  assert.equal(input.events.length, 0)
})

test('send-message uses an isolated explicit send action', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_message',
    idempotencyKey: 'idem-3',
    requestDigest: 'digest-3',
    messageText: 'hello',
    confirmationToken: 'confirm-2',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
  })

  assert.equal(result.status, 'succeeded')
  assert.equal(result.stage, 'message_sent')
  assert.equal(result.messageSent, true)
  assert.deepEqual(input.events, [
    { type: 'hotkey', payload: ['Enter'] },
  ])
})
