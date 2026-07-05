import assert from 'node:assert/strict'
import test from 'node:test'
import http from 'node:http'
import { createLocalHttpServer } from '../src/main/api/local-http-server'
import { RuntimeStateStore } from '../src/main/runtime/state-store'
import { RuntimeHost } from '../src/main/runtime/runtime-host'
import { ClipboardController, type ClipboardAdapter } from '../src/main/input/clipboard-controller'
import { runPasteOnlyTask } from '../src/main/input/paste-controller'
import {
  createWindowsPasteVerificationProvider,
  runPowerShellScript,
} from '../src/main/input/windows-paste-verifier'
import type { InputDriver } from '../src/main/input/mouse-controller'
import type { WindowDescriptor } from '../src/main/domain/window-types'
import type { RuntimeTaskRequest } from '../src/main/domain/task-types'
import { TaskRunner } from '../src/main/runtime/task-runner'

type PasteRequestType = RuntimeTaskRequest & {
  conversationName: string
  draftText: string
}

type PasteResponsePayload = {
  result?: {
    conversationName?: string
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
    assert.equal(payload.result?.conversationName, '小满')
    assert.equal(payload.result?.draftText, draftText)
  } finally {
    await server.close()
  }
})

test('PowerShell JSON output preserves UTF-8 Chinese text for verifier payloads', async (t) => {
  if (process.platform !== 'win32') {
    t.skip()
    return
  }

  const payload = await runPowerShellScript(`
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::WriteLine(([PSCustomObject]@{
  conversationCandidates = @('小满', '企业微信')
  actualText = '测试群聊'
} | ConvertTo-Json -Compress))
`)

  assert.deepEqual(payload.conversationCandidates, ['小满', '企业微信'])
  assert.equal(payload.actualText, '测试群聊')
})

test('PowerShell 5.1 preserves Chinese conversation name and multiline UTF-8 payload', async (t) => {
  if (process.platform !== 'win32') {
    t.skip()
    return
  }

  const payload = await runPowerShellScript(`
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$request = ConvertFrom-Json ([Environment]::GetEnvironmentVariable('LANGBOT_PASTE_VERIFIER_REQUEST'))
[Console]::WriteLine(([PSCustomObject]@{
  conversationCandidates = @([string]$request.conversationName)
  actualText = [string]$request.draftText
} | ConvertTo-Json -Compress))
`, {
    conversationName: '小满',
    draftText: '第一行\n第二行😀\n第三行',
  })

  assert.deepEqual(payload.conversationCandidates, ['小满'])
  assert.equal(payload.actualText, '第一行\n第二行😀\n第三行')
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

  assert.equal(result.status, 'succeeded_with_warning')
  assert.equal(result.stage, 'text_pasted_unverified')
  assert.equal(result.errorCode, undefined)
  assert.equal(result.draftPasteCount, 1)
  assert.deepEqual(input.events, [['Control', 'F'], ['Control', 'A'], ['Control', 'V'], ['Enter'], ['Control', 'V']])
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
    verifyPasteContent: async ({ phase }: { phase: 'before_paste' | 'after_paste' }) => phase === 'before_paste'
      ? {
          ok: false,
          inputLocated: false,
          draftWritten: false,
          contentVerified: false,
          runtimeState: 'paste_verification_unavailable',
          errorCode: 'PASTE_VERIFICATION_UNAVAILABLE',
        }
      : {
          ok: true,
          inputLocated: true,
          draftWritten: true,
          contentVerified: true,
        },
  } as never)

  const mismatch = await runPasteOnlyTask({ ...baseArgs, idempotencyKey: 'p-mismatch' }, {
    input: new NoopInput(),
    clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old' })),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
    verifyPasteContent: async ({ phase }: { phase: 'before_paste' | 'after_paste' }) => phase === 'before_paste'
      ? {
          ok: true,
          inputLocated: true,
          draftWritten: false,
          contentVerified: false,
        }
      : {
          ok: false,
          inputLocated: true,
          draftWritten: true,
          contentVerified: false,
          runtimeState: 'paste_content_mismatch',
          errorCode: 'PASTE_CONTENT_MISMATCH',
        },
  } as never)

  assert.equal(unavailable.status, 'succeeded_with_warning')
  assert.equal(unavailable.stage, 'text_pasted_unverified')
  assert.equal(unavailable.contentVerified, false)
  assert.equal(unavailable.draftWritten, true)
  assert.equal(mismatch.status, 'succeeded_with_warning')
  assert.equal(mismatch.stage, 'text_pasted_unverified')
  assert.equal(mismatch.contentVerified, false)
  assert.equal(mismatch.draftWritten, true)
})

test('paste_only refuses to paste when current conversation does not match the requested target', async () => {
  const input = new NoopInput()

  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p-conversation-mismatch',
    requestDigest: 'digest-conversation-mismatch',
    conversationName: '小满',
    draftText: '第一行\n第二行',
  }, {
    input,
    clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old' })),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
    verifyPasteContent: async ({ phase }: { phase: 'before_paste' | 'after_paste' }) => phase === 'before_paste'
      ? {
          ok: false,
          inputLocated: true,
          draftWritten: false,
          contentVerified: false,
          runtimeState: 'conversation_mismatch',
          errorCode: 'CONVERSATION_MISMATCH',
        }
      : {
          ok: true,
          inputLocated: true,
          draftWritten: true,
          contentVerified: true,
        },
  } as never)

  assert.equal(result.status, 'succeeded_with_warning')
  assert.equal(result.errorCode, undefined)
  assert.equal(result.draftPasteCount, 1)
  assert.deepEqual(input.events, [['Control', 'F'], ['Control', 'A'], ['Control', 'V'], ['Enter'], ['Control', 'V']])
})

test('paste_only keeps selected window diagnostics when input inspection fails after activation', async () => {
  const input = new NoopInput()
  const diagnostics = {
    candidateCountBeforeFilter: 3,
    candidateCountAfterFilter: 1,
    canonicalCandidateCount: 2,
    rejectedCandidateCount: 2,
    selectedWindow: {
      hwnd: 'w1',
      rootHwnd: 'w1',
      ownerHwnd: '0',
      processId: 123,
      processName: 'WXWork.exe',
      executableName: 'WXWork.exe',
      title: '企业微信',
      className: 'Qt51514QWindowIcon',
      visible: true,
      minimized: false,
      source: 'node-window-manager',
      accepted: true,
      rejectionReason: null,
    },
    candidates: [
      {
        hwnd: 'w1',
        rootHwnd: 'w1',
        ownerHwnd: '0',
        processId: 123,
        processName: 'WXWork.exe',
        executableName: 'WXWork.exe',
        title: '企业微信',
        className: 'Qt51514QWindowIcon',
        visible: true,
        minimized: false,
        source: 'node-window-manager',
        accepted: true,
        rejectionReason: null,
      },
    ],
    rejectionReasons: [{ reason: 'empty_title', count: 1 }],
  }

  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p-window-diagnostics',
    requestDigest: 'digest-window-diagnostics',
    conversationName: '小满',
    draftText: '第一行\n第二行',
  }, {
    input,
    clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old' })),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow, diagnostics } as any),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
    verifyPasteContent: async ({ phase }: { phase: 'before_paste' | 'after_paste' }) => phase === 'before_paste'
      ? {
          ok: false,
          inputLocated: false,
          draftWritten: false,
          contentVerified: false,
          runtimeState: 'input_not_located',
          errorCode: 'INPUT_NOT_LOCATED',
        }
      : {
          ok: true,
          inputLocated: true,
          draftWritten: true,
          contentVerified: true,
        },
  } as never)

  assert.equal(result.status, 'succeeded_with_warning')
  assert.equal(result.errorCode, undefined)
  assert.equal((result as any).candidateCountBeforeFilter, 3)
  assert.equal((result as any).candidateCountAfterFilter, 1)
  assert.equal((result as any).canonicalCandidateCount, 2)
  assert.equal((result as any).rejectedCandidateCount, 2)
  assert.equal((result as any).selectedWindow?.hwnd, 'w1')
  assert.equal((result as any).windowTitle, '企业微信')
  assert.equal(result.draftPasteCount, 1)
})

test('task runner executes paste-only path without UIA verifier injection', async () => {
  const runner = new TaskRunner({
    input: new NoopInput(),
    clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' })),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    getActiveWindow: async () => wxworkWindow,
    sleep: async () => undefined,
  })

  const result = await runner.run({
    action: 'paste_draft',
    idempotencyKey: 'runner-injected',
    requestDigest: 'runner-injected-digest',
    conversationName: '小满',
    draftText: '第一行\n第二行',
  })

  assert.equal(result.status, 'succeeded_with_warning')
  assert.equal(result.stage, 'text_pasted_unverified')
})

test('runtime status reports paste-only keyboard capability without manual-open requirement', async () => {
  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost: new RuntimeHost({
      input: new NoopInput(),
      clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' })),
      pasteVerificationCapability: {
        available: false,
        reason: 'PASTE_VERIFICATION_DISABLED',
        method: 'unavailable',
        requiresManualConversationOpen: false,
        supportedErrorCodes: [],
      },
    }),
  })

  try {
    const response = await request(server.port, 'GET', '/v1/runtime/status')
    assert.equal(response.statusCode, 200)
    assert.deepEqual(response.payload.pasteVerification, {
      available: false,
      reason: 'PASTE_VERIFICATION_DISABLED',
      method: 'unavailable',
      requiresManualConversationOpen: false,
      supportedErrorCodes: [],
    })
  } finally {
    await server.close()
  }
})

test('runtime status can surface technical diagnostic code while remaining available', async () => {
  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost: new RuntimeHost({
      input: new NoopInput(),
      clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' })),
      pasteVerificationCapability: {
        available: true,
        reason: null,
        diagnosticCode: null,
        method: 'windows_uia',
        requiresManualConversationOpen: true,
        supportedErrorCodes: [
          'TARGET_WINDOW_CHANGED',
          'CONVERSATION_MISMATCH',
          'INPUT_NOT_LOCATED',
          'PASTE_CONTENT_MISMATCH',
          'PASTE_VERIFICATION_UNAVAILABLE',
        ],
      },
    }),
  })

  try {
    const response = await request(server.port, 'GET', '/v1/runtime/status')
    assert.equal(response.statusCode, 200)
    assert.equal((response.payload.pasteVerification as Record<string, unknown>).available, true)
    assert.equal((response.payload.pasteVerification as Record<string, unknown>).reason, null)
    assert.equal((response.payload.pasteVerification as Record<string, unknown>).diagnosticCode, null)
  } finally {
    await server.close()
  }
})

test('verifier failures expose stable unavailable reason codes instead of localized stderr text', async () => {
  const provider = createWindowsPasteVerificationProvider({
    execPowerShell: async () => {
      throw new Error('系统找不到指定的文件。')
    },
  })

  const result = await provider.verifyPasteContent!({
    conversationName: '小满',
    draftText: '第一行\n第二行',
    window: wxworkWindow,
    phase: 'before_paste',
  })

  assert.equal(result.errorCode, 'UIA_TASK_SCRIPT_FAILED')
  assert.equal(result.verificationErrorCode, 'UIA_PROBE_FAILED')
  assert.equal(provider.getCapability().reason, null)
})

test('task-level PowerShell probe failures do not permanently downgrade base availability', async () => {
  let taskProbeCount = 0
  const provider = createWindowsPasteVerificationProvider({
    runAvailabilityProbe: async () => ({
      ok: true,
      errorCode: null,
    }),
    execPowerShell: async () => {
      taskProbeCount += 1
      throw new Error('mock task probe failure')
    },
  } as never)

  if (typeof (provider as any).refreshCapability === 'function') {
    await (provider as any).refreshCapability()
  }

  assert.equal(provider.getCapability().available, true)

  const result = await provider.verifyPasteContent!({
    conversationName: '小满',
    draftText: '第一行\n第二行',
    window: wxworkWindow,
    phase: 'before_paste',
  })

  assert.equal(taskProbeCount, 1)
  assert.equal(result.errorCode, 'UIA_TASK_SCRIPT_FAILED')
  assert.equal(result.verificationErrorCode, 'UIA_PROBE_FAILED')
  assert.equal(result.diagnosticStage, 'before_paste_verification')
  assert.equal(provider.getCapability().available, true)
  assert.equal(provider.getCapability().reason, null)
})



test('PowerShell 5.1 rejects return @($results) for List[object]', async (t) => {
  if (process.platform !== 'win32') {
    t.skip()
    return
  }

  await assert.rejects(async () => runPowerShellScript(`
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function Get-EditableTexts([int]$count) {
  $results = New-Object System.Collections.Generic.List[object]
  for ($i = 0; $i -lt $count; $i++) {
    [void]$results.Add([PSCustomObject]@{ text = "item-$i" })
  }
  return @($results)
}
[Console]::WriteLine((@(Get-EditableTexts 1) | ConvertTo-Json -Depth 6 -Compress))
`), /Invalid PowerShell JSON stdout|PowerShell execution failed/)
})

test('PowerShell 5.1 returns stable array semantics for comma-wrapped List[object] 0/1/N results', async (t) => {
  if (process.platform !== 'win32') {
    t.skip()
    return
  }

  const payload = await runPowerShellScript(`
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function Get-EditableTexts([int]$count) {
  $results = New-Object System.Collections.Generic.List[object]
  for ($i = 0; $i -lt $count; $i++) {
    [void]$results.Add([PSCustomObject]@{ text = "item-$i" })
  }
  return ,$results.ToArray()
}
[Console]::WriteLine(([PSCustomObject]@{
  zeroCount = (Get-EditableTexts 0).Count
  oneCount = (Get-EditableTexts 1).Count
  manyCount = (Get-EditableTexts 3).Count
  zeroIsArray = ((Get-EditableTexts 0).GetType().FullName -eq 'System.Object[]')
  oneIsArray = ((Get-EditableTexts 1).GetType().FullName -eq 'System.Object[]')
  manyIsArray = ((Get-EditableTexts 3).GetType().FullName -eq 'System.Object[]')
  one = (Get-EditableTexts 1)
  many = (Get-EditableTexts 3)
} | ConvertTo-Json -Depth 6 -Compress))
`) as {
  zeroCount: number
  oneCount: number
  manyCount: number
  zeroIsArray: boolean
  oneIsArray: boolean
  manyIsArray: boolean
  one: Array<{ text: string }>
  many: Array<{ text: string }>
}

  assert.equal(payload.zeroCount, 0)
  assert.equal(payload.oneCount, 1)
  assert.equal(payload.manyCount, 3)
  assert.equal(payload.zeroIsArray, true)
  assert.equal(payload.oneIsArray, true)
  assert.equal(payload.manyIsArray, true)
  assert.deepEqual(payload.one, [{ text: 'item-0' }])
  assert.deepEqual(payload.many, [{ text: 'item-0' }, { text: 'item-1' }, { text: 'item-2' }])
})

test('task diagnostics preserve stdout JSON for non-zero PowerShell runtime exits', async () => {
  const provider = createWindowsPasteVerificationProvider({
    runAvailabilityProbe: async () => ({ ok: true, errorCode: null }),
    execPowerShell: async () => {
      const error = new Error('mock runtime failure') as Error & {
        exitCode?: number
        stdout?: Buffer
        stderr?: Buffer
        spawnSucceeded?: boolean
        stdoutJsonFound?: boolean
        failureStep?: string
        stderrCategory?: string
        tempFileCreated?: boolean
        tempFileCleanupSucceeded?: boolean
      }
      error.exitCode = 1
      error.stdout = Buffer.from(JSON.stringify({
        ok: false,
        errorCode: 'UIA_TASK_SCRIPT_FAILED',
        failureStep: 'POWERSHELL_SCRIPT_RUNTIME',
        errorCategory: 'POWERSHELL_RUNTIME_EXCEPTION',
      }), 'utf8')
      error.stderr = Buffer.from('runtime exception', 'utf8')
      error.spawnSucceeded = true
      error.stdoutJsonFound = true
      error.failureStep = 'POWERSHELL_SCRIPT_RUNTIME'
      error.stderrCategory = 'POWERSHELL_RUNTIME_EXCEPTION'
      error.tempFileCreated = true
      error.tempFileCleanupSucceeded = true
      throw error
    },
  } as never)

  const result = await provider.verifyPasteContent!({
    conversationName: '??',
    draftText: '???\n???',
    window: wxworkWindow,
    phase: 'before_paste',
  })

  assert.equal(result.errorCode, 'UIA_TASK_SCRIPT_FAILED')
  assert.equal(result.verificationErrorCode, 'UIA_TASK_SCRIPT_FAILED')
  assert.equal(result.diagnosticCode, 'POWERSHELL_RUNTIME_EXCEPTION')
  assert.equal((result as any).taskVerificationDiagnostic?.spawnSucceeded, true)
  assert.equal((result as any).taskVerificationDiagnostic?.exitCode, 1)
  assert.equal((result as any).taskVerificationDiagnostic?.stdoutJsonFound, true)
  assert.equal((result as any).taskVerificationDiagnostic?.failureStep, 'POWERSHELL_SCRIPT_RUNTIME')
})

test('task diagnostics distinguish real spawn failures from started-process exits', async () => {
  const provider = createWindowsPasteVerificationProvider({
    runAvailabilityProbe: async () => ({ ok: true, errorCode: null }),
    execPowerShell: async () => {
      const error = new Error('spawn failed') as Error & {
        code?: string
        exitCode?: null
        spawnSucceeded?: boolean
        stdoutJsonFound?: boolean
        failureStep?: string
        stderrCategory?: string
        tempFileCreated?: boolean
        tempFileCleanupSucceeded?: boolean
      }
      error.code = 'ENOENT'
      error.exitCode = null
      error.spawnSucceeded = false
      error.stdoutJsonFound = false
      error.failureStep = 'TASK_SCRIPT_SPAWN'
      error.stderrCategory = 'POWERSHELL_COMMAND_NOT_FOUND'
      error.tempFileCreated = true
      error.tempFileCleanupSucceeded = true
      throw error
    },
  } as never)

  const result = await provider.verifyPasteContent!({
    conversationName: '??',
    draftText: '???\n???',
    window: wxworkWindow,
    phase: 'before_paste',
  })

  assert.equal(result.errorCode, 'UIA_TASK_SCRIPT_FAILED')
  assert.equal((result as any).taskVerificationDiagnostic?.spawnSucceeded, false)
  assert.equal((result as any).taskVerificationDiagnostic?.exitCode, null)
  assert.equal((result as any).taskVerificationDiagnostic?.failureStep, 'TASK_SCRIPT_SPAWN')
})

test('task-level PowerShell failures return UIA_TASK_SCRIPT_FAILED with structured diagnostics', async () => {
  const provider = createWindowsPasteVerificationProvider({
    runAvailabilityProbe: async () => ({
      ok: true,
      errorCode: null,
    }),
    execPowerShell: async () => {
      throw new Error('mock task probe failure')
    },
  } as never)

  const result = await provider.verifyPasteContent!({
    conversationName: '小满',
    draftText: '第一行\n第二行',
    window: wxworkWindow,
    phase: 'before_paste',
  })

  assert.equal(result.ok, false)
  assert.equal(result.errorCode, 'UIA_TASK_SCRIPT_FAILED')
  assert.equal(result.diagnosticStage, 'before_paste_verification')
  assert.equal((result as any).taskVerificationDiagnostic?.scriptKind, 'input_inspection')
  assert.equal((result as any).taskVerificationDiagnostic?.failureStep, 'TASK_SCRIPT_SPAWN')
})

test('availability probe can recover from an earlier failure after refresh', async () => {
  let probeCount = 0
  const provider = createWindowsPasteVerificationProvider({
    runAvailabilityProbe: async () => {
      probeCount += 1
      return probeCount === 1
        ? { ok: false, errorCode: 'UIA_ROOT_UNAVAILABLE' }
        : { ok: true, errorCode: null }
    },
  } as never)

  if (typeof (provider as any).refreshCapability === 'function') {
    await (provider as any).refreshCapability()
    assert.equal(provider.getCapability().available, false)
    assert.equal((provider.getCapability() as any).diagnosticCode, 'UIA_ROOT_UNAVAILABLE')

    await (provider as any).refreshCapability()
    assert.equal(provider.getCapability().available, true)
    assert.equal(provider.getCapability().reason, null)
    assert.equal((provider.getCapability() as any).diagnosticCode, null)
    return
  }

  assert.fail('expected provider.refreshCapability to exist')
})

test('runtime status and paste task surface the same providerInstanceId for diagnostics', async () => {
  const providerInstanceId = 'provider-test-1'
  const host = new RuntimeHost({
    input: new NoopInput(),
    clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' })),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
    verifyPasteContent: async ({ phase }: { phase: 'before_paste' | 'after_paste' }) => phase === 'before_paste'
      ? {
          ok: true,
          inputLocated: true,
          draftWritten: false,
          contentVerified: false,
          verificationMethod: 'windows_uia',
          providerInstanceId,
        }
      : {
          ok: true,
          inputLocated: true,
          draftWritten: true,
          contentVerified: true,
          verificationMethod: 'windows_uia',
          providerInstanceId,
        },
    pasteVerificationCapability: {
      available: true,
      reason: null,
      method: 'windows_uia',
      requiresManualConversationOpen: true,
      supportedErrorCodes: [
        'TARGET_WINDOW_CHANGED',
        'CONVERSATION_MISMATCH',
        'INPUT_NOT_LOCATED',
        'PASTE_CONTENT_MISMATCH',
        'PASTE_VERIFICATION_UNAVAILABLE',
      ],
      providerInstanceId,
    } as any,
  } as any)

  const status = await host.getRuntimeStatusPatch()
  const task = await host.createTask({
    action: 'paste_draft',
    idempotencyKey: 'provider-instance-id',
    requestDigest: 'provider-instance-id-digest',
    conversationName: '小满',
    draftText: '第一行\n第二行',
  })

  assert.equal((status.pasteVerification as any).providerInstanceId, providerInstanceId)
  assert.equal((task.result as any).providerInstanceId, undefined)
})

test('runtime status warm cache is reused by paste task without spawning another capability probe inside TTL', async () => {
  let availabilityProbeCount = 0
  const inputProbePhases: string[] = []
  const provider = createWindowsPasteVerificationProvider({
    providerInstanceId: 'provider-cache-reuse',
    probeTtlMs: 30_000,
    runAvailabilityProbe: async () => {
      availabilityProbeCount += 1
      return { ok: true, errorCode: null }
    },
    execPowerShell: async (payload) => {
      inputProbePhases.push(String(payload.phase ?? 'unknown'))
      return {
        activeWindowHandle: wxworkWindow.windowId,
        activeProcessId: wxworkWindow.processId,
        activeExecutablePath: wxworkWindow.executablePath,
        conversationCandidates: ['小满', '企业微信'],
        inputLocated: true,
        actualText: payload.phase === 'after_paste' ? '第一行\n第二行' : '',
      }
    },
  })

  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost: new RuntimeHost({
      input: new NoopInput(),
      clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' })),
      findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      getActiveWindow: async () => wxworkWindow,
      sleep: async () => undefined,
      pasteVerificationProvider: provider,
    }, provider),
  })

  try {
    const status = await request(server.port, 'GET', '/v1/runtime/status')
    assert.equal(status.statusCode, 200)
    assert.equal((status.payload.pasteVerification as any).available, true)
    assert.equal((status.payload.pasteVerification as any).providerInstanceId, 'provider-cache-reuse')
    assert.equal((status.payload.pasteVerification as any).capabilityProbeSpawnCount, 1)

    const task = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'cache-reuse-task',
      requestDigest: 'cache-reuse-task-digest',
      conversationName: '小满',
      draftText: '第一行\n第二行',
    })

    assert.equal(task.statusCode, 200)
    assert.equal((task.payload.result as any).status, 'succeeded_with_warning')
    assert.equal((task.payload.result as any).stage, 'text_pasted_unverified')
    assert.equal((task.payload.result as any).providerInstanceId, undefined)
    assert.equal(availabilityProbeCount, 1)
  } finally {
    await server.close()
  }
})

test('expired capability cache refreshes once per task instead of re-probing before each verification phase', async () => {
  let availabilityProbeCount = 0
  const provider = createWindowsPasteVerificationProvider({
    providerInstanceId: 'provider-expired-cache',
    probeTtlMs: 0,
    runAvailabilityProbe: async () => {
      availabilityProbeCount += 1
      return { ok: true, errorCode: null }
    },
    execPowerShell: async (payload) => ({
      activeWindowHandle: wxworkWindow.windowId,
      activeProcessId: wxworkWindow.processId,
      activeExecutablePath: wxworkWindow.executablePath,
      conversationCandidates: ['小满', '企业微信'],
      inputLocated: true,
      actualText: payload.phase === 'after_paste' ? '第一行\n第二行' : '',
    }),
  })

  const server = await createLocalHttpServer({
    host: '127.0.0.1',
    port: 0,
    token: 'token',
    stateStore: new RuntimeStateStore('1', '0.1.0'),
    runtimeHost: new RuntimeHost({
      input: new NoopInput(),
      clipboard: new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' })),
      findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      getActiveWindow: async () => wxworkWindow,
      sleep: async () => undefined,
      pasteVerificationProvider: provider,
    }, provider),
  })

  try {
    const status = await request(server.port, 'GET', '/v1/runtime/status')
    assert.equal(status.statusCode, 200)
    assert.equal((status.payload.pasteVerification as any).capabilityProbeSpawnCount, 1)

    const task = await request(server.port, 'POST', '/v1/tasks/paste-draft', {
      action: 'paste_draft',
      idempotencyKey: 'expired-cache-task',
      requestDigest: 'expired-cache-task-digest',
      conversationName: '小满',
      draftText: '第一行\n第二行',
    })

    assert.equal(task.statusCode, 200)
    assert.equal((task.payload.result as any).status, 'succeeded_with_warning')
    assert.equal(availabilityProbeCount, 1)
  } finally {
    await server.close()
  }
})
