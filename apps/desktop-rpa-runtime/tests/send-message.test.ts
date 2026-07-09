import assert from 'node:assert/strict'
import test from 'node:test'
import { ClipboardController, type ClipboardAdapter } from '../src/main/input/clipboard-controller'
import { runSendMessageTask } from '../src/main/input/send-controller'
import type { WindowDescriptor } from '../src/main/domain/window-types'

class RecordingInputDriver {
  readonly events: Array<{ type: string; payload: unknown }> = []
  async click(point: { x: number; y: number }): Promise<void> { this.events.push({ type: 'click', payload: point }) }
  async hotkey(keys: string[]): Promise<void> { this.events.push({ type: 'hotkey', payload: keys }) }
  async typeText(text: string): Promise<void> { this.events.push({ type: 'typeText', payload: text }) }
}

function fakeClipboardAdapter(formats: string[], data: Record<string, string> = {}): ClipboardAdapter {
  return {
    availableFormats: () => formats,
    readText: () => data.text ?? '',
    readHTML: () => data.html ?? '',
    readRTF: () => data.rtf ?? '',
    readImage: () => ({ isEmpty: () => !data.image, toDataURL: () => data.image ?? '' }),
    write: (next) => { Object.assign(data, next) },
    writeText: (text) => { data.text = text },
  }
}

const wxworkWindow: WindowDescriptor = {
  appType: 'wework',
  windowId: 'w1',
  ownerWindowId: '0',
  rootWindowId: 'w1',
  title: '企业微信',
  executablePath: 'C:/Program Files/WXWork/WXWork.exe',
  processName: 'WXWork.exe',
  processId: 123,
  displayId: 1,
  boundsLogical: { x: 0, y: 0, width: 1000, height: 800 },
  clientBounds: { x: 0, y: 0, width: 1000, height: 800 },
  scaleFactor: 1,
  isVisible: true,
  isMinimized: false,
  className: 'Qt51514QWindowIcon',
  source: 'node-window-manager',
}

function buildPreparedResult(overrides: Record<string, unknown> = {}) {
  return {
    status: 'succeeded',
    stage: 'prepared_for_send',
    messageSent: false,
    sendAuthorized: false,
    inputLocated: true,
    draftWritten: true,
    contentVerified: true,
    attachmentsPrepared: false,
    attachmentPasteRequested: false,
    attachmentsVerified: true,
    evidence: [{ step: 'prepare', ok: true }],
    ...overrides,
  }
}

function buildPostVerifyResult(overrides: Record<string, unknown> = {}) {
  return {
    verified: true,
    verification_method: 'input_cleared',
    verification_result: 'input_cleared',
    error_code: undefined,
    error_message: undefined,
    evidence: [{ step: 'post_send_verify', ok: true }],
    ...overrides,
  }
}

test('send_draft does not require a token and returns sent after verified Enter flow', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_draft',
    idempotencyKey: 'idem-1',
    requestDigest: 'digest-1',
    conversationName: 'Customer A',
    draftText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    prepareDraftInput: async () => buildPreparedResult(),
    postSendVerify: async () => buildPostVerifyResult(),
  } as never)

  assert.equal(result.status, 'succeeded')
  assert.equal(result.stage, 'sent')
  assert.equal(result.outcome, 'sent')
  assert.equal(result.enter_dispatched, true)
  assert.equal(result.post_send_verified, true)
  assert.equal(result.verification_method, 'input_cleared')
  assert.equal(result.verification_result, 'input_cleared')
  assert.equal(result.error_code, undefined)
  assert.equal(Array.isArray(result.evidence), true)
  assert.deepEqual(input.events, [
    { type: 'hotkey', payload: ['Enter'] },
  ])
})

test('send-message remains blocked when force-disable-send is enabled', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_message',
    idempotencyKey: 'idem-2',
    requestDigest: 'digest-2',
    conversationName: 'Customer A',
    messageText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: true,
  })

  assert.equal(result.status, 'blocked')
  assert.equal(result.errorCode, 'SEND_DRIVER_DISABLED')
  assert.equal(input.events.length, 0)
})

test('send_draft does not press Enter when text preparation fails', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_draft',
    idempotencyKey: 'idem-3',
    requestDigest: 'digest-3',
    conversationName: 'Customer A',
    draftText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    prepareDraftInput: async () => buildPreparedResult({
      status: 'failed',
      stage: 'pasting_text',
      errorCode: 'TEXT_PASTE_FAILED',
      errorMessage: 'text failed',
      evidence: [{ step: 'prepare', ok: false, stage: 'pasting_text' }],
    }),
  } as never)

  assert.equal(result.status, 'failed')
  assert.equal(result.outcome, 'failed')
  assert.equal(result.enter_dispatched, false)
  assert.equal(result.post_send_verified, false)
  assert.equal(result.error_code, 'TEXT_PASTE_FAILED')
  assert.equal(result.verification_result, 'not_run')
  assert.deepEqual(input.events, [])
})

test('send_draft does not press Enter when any attachment preparation fails', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_draft',
    idempotencyKey: 'idem-4',
    requestDigest: 'digest-4',
    conversationName: 'Customer A',
    draftText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    prepareDraftInput: async () => buildPreparedResult({
      status: 'failed',
      stage: 'pasting_attachments',
      errorCode: 'ATTACHMENT_PASTE_FAILED',
      errorMessage: 'attachment failed',
      attachmentsPrepared: false,
      attachmentPasteRequested: false,
      attachmentsVerified: false,
      evidence: [{ step: 'prepare', ok: false, stage: 'pasting_attachments' }],
    }),
  } as never)

  assert.equal(result.status, 'failed')
  assert.equal(result.outcome, 'failed')
  assert.equal(result.enter_dispatched, false)
  assert.equal(result.post_send_verified, false)
  assert.equal(result.error_code, 'ATTACHMENT_PASTE_FAILED')
  assert.deepEqual(input.events, [])
})

test('send_draft does not press Enter when pre-send verification fails', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_draft',
    idempotencyKey: 'idem-5',
    requestDigest: 'digest-5',
    conversationName: 'Customer A',
    draftText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    prepareDraftInput: async () => buildPreparedResult({
      status: 'failed',
      stage: 'before_send_verification',
      errorCode: 'INPUT_CONTENT_UNVERIFIED',
      errorMessage: 'verification failed',
      contentVerified: false,
      evidence: [{ step: 'prepare', ok: false, stage: 'before_send_verification' }],
    }),
  } as never)

  assert.equal(result.status, 'failed')
  assert.equal(result.outcome, 'failed')
  assert.equal(result.enter_dispatched, false)
  assert.equal(result.post_send_verified, false)
  assert.equal(result.error_code, 'INPUT_CONTENT_UNVERIFIED')
  assert.deepEqual(input.events, [])
})

test('send_draft returns failed when Enter dispatch throws', async () => {
  const input = new RecordingInputDriver()
  input.hotkey = async () => {
    throw new Error('ENTER_DISPATCH_FAILED')
  }

  const result = await runSendMessageTask({
    action: 'send_draft',
    idempotencyKey: 'idem-6',
    requestDigest: 'digest-6',
    conversationName: 'Customer A',
    draftText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    prepareDraftInput: async () => buildPreparedResult(),
  } as never)

  assert.equal(result.status, 'failed')
  assert.equal(result.outcome, 'failed')
  assert.equal(result.enter_dispatched, false)
  assert.equal(result.post_send_verified, false)
  assert.equal(result.error_code, 'ENTER_DISPATCH_FAILED')
})

test('send_draft returns unknown when Enter is dispatched but post-send verification cannot confirm delivery', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_draft',
    idempotencyKey: 'idem-7',
    requestDigest: 'digest-7',
    conversationName: 'Customer A',
    draftText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    prepareDraftInput: async () => buildPreparedResult(),
    postSendVerify: async () => buildPostVerifyResult({
      verified: false,
      verification_result: 'not_confirmed',
      error_code: 'POST_SEND_VERIFICATION_FAILED',
      error_message: 'unable to confirm',
      evidence: [{ step: 'post_send_verify', ok: false }],
    }),
  } as never)

  assert.equal(result.status, 'succeeded_with_warning')
  assert.equal(result.stage, 'sent_unconfirmed')
  assert.equal(result.outcome, 'unknown')
  assert.equal(result.enter_dispatched, true)
  assert.equal(result.post_send_verified, false)
  assert.equal(result.messageSent, null)
  assert.equal(result.terminal_confirmed, false)
  assert.equal(result.retry_allowed, false)
  assert.deepEqual(input.events, [
    { type: 'hotkey', payload: ['Enter'] },
  ])
})

test('send_draft presses Enter at most once', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_draft',
    idempotencyKey: 'idem-8',
    requestDigest: 'digest-8',
    conversationName: 'Customer A',
    draftText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    prepareDraftInput: async () => buildPreparedResult({
      attachmentsPrepared: true,
      attachmentPasteRequested: true,
      attachmentsVerified: true,
    }),
    postSendVerify: async () => buildPostVerifyResult(),
  } as never)

  assert.equal(result.outcome, 'sent')
  assert.equal(input.events.length, 1)
  assert.deepEqual(input.events[0], { type: 'hotkey', payload: ['Enter'] })
})

test('send_message searches once, pastes once, waits fixed delays, and dispatches the final Enter exactly once', async () => {
  const input = new RecordingInputDriver()
  const sleeps: number[] = []
  const clipboardWrites: string[] = []
  let verifierCalls = 0
  const clipboard = new ClipboardController(undefined, {
    ...fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }),
    writeText(text: string) {
      clipboardWrites.push(text)
    },
    readText() {
      return clipboardWrites.at(-1) ?? 'old clipboard'
    },
  })
  const result = await runSendMessageTask({
    action: 'send_message',
    idempotencyKey: 'idem-9',
    requestDigest: 'digest-9',
    conversationName: 'Customer A',
    messageText: 'hello',
  }, {
    input: input as never,
    clipboard,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    getActiveWindow: async () => wxworkWindow,
    sleep: async (ms: number) => { sleeps.push(ms) },
    pasteVerificationProvider: {
      getCapability: () => {
        verifierCalls += 1
        return {
          available: true,
          reason: null,
          method: 'windows_uia',
          requiresManualConversationOpen: true,
          supportedErrorCodes: ['INPUT_NOT_LOCATED', 'CONVERSATION_MISMATCH'],
        }
      },
      verifyInputContent: async () => {
        verifierCalls += 1
        throw new Error('verifier should not run')
      },
    } as never,
  } as never)

  assert.equal(result.status, 'succeeded_with_warning')
  assert.equal(result.stage, 'sent_unconfirmed')
  assert.equal(result.sendKeyCount, 1)
  assert.equal(result.send_key_count, 1)
  assert.equal(result.enter_dispatched, true)
  assert.equal(result.messageSent, null)
  assert.equal(result.terminal_confirmed, false)
  assert.equal(result.retry_allowed, false)
  assert.equal(verifierCalls, 0)
  assert.deepEqual(sleeps, [300, 200, 300, 800, 150])
  assert.deepEqual(clipboardWrites, ['hello'])
  assert.deepEqual(input.events, [
    { type: 'hotkey', payload: ['Control', 'F'] },
    { type: 'hotkey', payload: ['Control', 'A'] },
    { type: 'typeText', payload: 'Customer A' },
    { type: 'hotkey', payload: ['Enter'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
    { type: 'hotkey', payload: ['Enter'] },
  ])
})

test('send_message does not dispatch Enter when prepare fails with TARGET_WINDOW_CHANGED', async () => {
  const input = new RecordingInputDriver()
  const result = await runSendMessageTask({
    action: 'send_message',
    idempotencyKey: 'idem-10',
    requestDigest: 'digest-10',
    conversationName: 'Customer A',
    messageText: 'hello',
  }, {
    input: input as never,
    runtimeAutoSendEnabled: true,
    sendDriverForceDisabled: false,
    prepareDraftInput: async () => buildPreparedResult({
      status: 'failed',
      stage: 'before_send_verification',
      errorCode: 'TARGET_WINDOW_CHANGED',
      errorMessage: 'target window changed',
      draftWritten: false,
      messageSent: false,
      evidence: [{ step: 'prepare', ok: false, stage: 'before_send_verification', error_code: 'TARGET_WINDOW_CHANGED' }],
    }),
  } as never)

  assert.equal(result.status, 'failed')
  assert.equal(result.error_code, 'TARGET_WINDOW_CHANGED')
  assert.equal(result.sendKeyCount, 0)
  assert.equal(result.enter_dispatched, false)
  assert.equal(result.messageSent, false)
  assert.deepEqual(input.events, [])
})
