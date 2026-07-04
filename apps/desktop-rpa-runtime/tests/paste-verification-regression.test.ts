import assert from 'node:assert/strict'
import test from 'node:test'
import http from 'node:http'
import { createLocalHttpServer } from '../src/main/api/local-http-server'
import { RuntimeStateStore } from '../src/main/runtime/state-store'
import { RuntimeHost } from '../src/main/runtime/runtime-host'
import { ClipboardController, type ClipboardAdapter } from '../src/main/input/clipboard-controller'
import { runPasteOnlyTask } from '../src/main/input/paste-controller'
import type { InputDriver } from '../src/main/input/mouse-controller'
import type { WindowDescriptor } from '../src/main/domain/window-types'
import type { RuntimeTaskRequest } from '../src/main/domain/task-types'

type PasteRequestType = RuntimeTaskRequest & {
  conversationName: string
  draftText: string
}

type PasteResponsePayload = {
  result?: {
    draftText?: string
  }
}

function isPasteRequestType(request: RuntimeTaskRequest): request is PasteRequestType {
  return typeof request.conversationName === 'string' && typeof request.draftText === 'string'
}

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

class NoopInput implements InputDriver {
  readonly events: string[][] = []
  async click(): Promise<void> {}
  async hotkey(keys: string[]): Promise<void> { this.events.push(keys) }
  async typeText(): Promise<void> {}
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
  ownerWindowId: null,
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
}

test('runtime paste-draft preserves UTF-8 unicode and newline payloads end-to-end', async () => {
  const captured: { request?: PasteRequestType } = {}
  const runtimeHost = {
    activeTaskCount: () => 0,
    getTask: () => null,
    cancelTask: () => null,
    async createTask(request: RuntimeTaskRequest) {
      assert.ok(isPasteRequestType(request))
      captured.request = request
      return {
        id: 'task-u8',
        status: 'queued',
        stage: 'queued',
        result: request,
      }
    },
  } as unknown as RuntimeHost

  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost,
  })

  try {
    const draftText = '【Broadcast Paste 内容保真复验】\nPASTE_INTEGRITY_0704_1\n中文 ABC 123，标点：，。！？【】\nemoji 😀👨‍👩‍👧‍👦\r\nline-end'
    const response = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'idem-u8',
      requestDigest: 'digest-u8',
      conversationName: '小满',
      draftText,
    })

    assert.equal(response.statusCode, 200)
    const capturedRequest = captured.request
    assert.ok(capturedRequest)
    assert.equal(capturedRequest.conversationName, '小满')
    assert.equal(capturedRequest.draftText, draftText)
    assert.equal(capturedRequest.draftText.includes('\\n'), false)
    const payload = response.payload as PasteResponsePayload
    assert.equal(payload.result?.draftText, draftText)
  } finally {
    await server.close()
  }
})

test('paste_only aborts before draft Ctrl+V when clipboard roundtrip mutates unicode/newlines', async () => {
  const input = new NoopInput()
  const clipboardData: Record<string, string> = { text: 'old clipboard' }
  const clipboard = new ClipboardController(undefined, {
    ...fakeClipboardAdapter(['text/plain'], clipboardData),
    writeText(text: string) {
      clipboardData.text = text.replace('第二行😀', '第二行?').replace(/\n/g, ' ')
    },
  })

  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p-u8',
    requestDigest: 'digest-u8',
    conversationName: '小满',
    draftText: '第一行\n第二行😀',
  }, {
    input,
    clipboard,
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
  } as never)

  assert.equal(result.status, 'interrupted')
  assert.equal(result.stage, 'clipboard_roundtrip_mismatch')
  assert.equal(result.errorCode, 'CLIPBOARD_ROUNDTRIP_MISMATCH')
  assert.equal(result.draftPasteCount, 0)
  assert.deepEqual(input.events, [
    ['Control', 'F'],
    ['Control', 'V'],
    ['Enter'],
  ])
})

test('paste_only distinguishes unavailable verification from content mismatch', async () => {
  const baseArgs = {
    action: 'paste_draft' as const,
    idempotencyKey: 'p-verify',
    requestDigest: 'digest-verify',
    conversationName: '小满',
    draftText: 'A\nB',
  }

  const unavailable = await runPasteOnlyTask(baseArgs, {
    input: new NoopInput(),
    clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old' })),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
    verifyPasteContent: async () => ({
      ok: false,
      inputLocated: false,
      draftWritten: false,
      contentVerified: false,
      runtimeState: 'paste_verification_unavailable',
      errorCode: 'PASTE_VERIFICATION_UNAVAILABLE',
    }),
  } as never)

  const mismatch = await runPasteOnlyTask({ ...baseArgs, idempotencyKey: 'p-mismatch' }, {
    input: new NoopInput(),
    clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old' })),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
    verifyPasteContent: async () => ({
      ok: false,
      inputLocated: true,
      draftWritten: true,
      contentVerified: false,
      runtimeState: 'paste_content_mismatch',
      errorCode: 'PASTE_CONTENT_MISMATCH',
    }),
  } as never)

  assert.equal(unavailable.errorCode, 'PASTE_VERIFICATION_UNAVAILABLE')
  assert.equal(unavailable.inputLocated, false)
  assert.equal(unavailable.draftWritten, false)
  assert.equal(mismatch.errorCode, 'PASTE_CONTENT_MISMATCH')
  assert.equal(mismatch.inputLocated, true)
  assert.equal(mismatch.draftWritten, true)
})
