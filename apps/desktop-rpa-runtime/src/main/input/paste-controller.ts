import { createHash } from 'node:crypto'
import type { RuntimeTaskRequest } from '../domain/task-types'
import type { WindowDescriptor } from '../domain/window-types'
import { activateWindow } from '../window/window-activator'
import { findUniqueVisibleWxWorkMainWindow } from '../window/window-finder'
import { ClipboardController } from './clipboard-controller'
import type { InputDriver } from './mouse-controller'

type TargetWindowResult =
  | { ok: true; window: WindowDescriptor }
  | { ok: false; errorCode: 'TARGET_WINDOW_NOT_FOUND'; candidates: WindowDescriptor[] }

export interface PasteTaskDeps {
  clipboard: ClipboardController
  input: InputDriver
  sleep?: (ms: number) => Promise<void>
  findTargetWindow?: () => Promise<TargetWindowResult>
  activateTargetWindow?: (window: WindowDescriptor) => Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }>
  verifyPasteContent?: (args: {
    conversationName: string
    draftText: string
    window: WindowDescriptor
  }) => Promise<PasteVerificationResult>
}

interface TextDiagnostics {
  textLengthUtf16: number
  codePointCount: number
  digest: string
  lineCount: number
  crCount: number
  lfCount: number
}

interface PasteVerificationResult {
  ok: boolean
  inputLocated: boolean
  draftWritten: boolean
  contentVerified: boolean
  runtimeState?: string
  errorCode?: string
  verificationMethod?: string
  verificationErrorCode?: string
  actualTextLength?: number
  actualCodePointCount?: number
  actualDigest?: string
  actualLineCount?: number
}

export async function runPasteOnlyTask(request: RuntimeTaskRequest, deps: PasteTaskDeps): Promise<Record<string, unknown>> {
  const conversationName = String(request.conversationName ?? '').trim()
  const draftText = String(request.draftText ?? '')
  if (!conversationName) return buildResult(request, 'blocked', 'queued', 'CONVERSATION_NAME_REQUIRED')
  if (!draftText.trim()) return buildResult(request, 'blocked', 'queued', 'DRAFT_TEXT_REQUIRED')

  const clipboardState = deps.clipboard.inspectRestorable()
  if (!clipboardState.ok) {
    return buildResult(request, 'blocked', 'queued', clipboardState.errorCode, {
      unsupportedFormats: clipboardState.unsupportedFormats,
    })
  }

  const sleep = deps.sleep ?? defaultSleep
  const findTargetWindow = deps.findTargetWindow ?? findUniqueVisibleWxWorkMainWindow
  const activateTargetWindow = deps.activateTargetWindow ?? activateWindow
  let status:
    | 'succeeded'
    | 'succeeded_with_warning'
    | 'blocked'
    | 'failed'
    | 'cancelled'
    | 'timed_out'
    | 'interrupted' = 'succeeded'
  let stage = 'queued'
  let errorCode: string | undefined
  let clipboardRestoreFailed = false
  let searchShortcutCount = 0
  let conversationPasteCount = 0
  let conversationConfirmEnterCount = 0
  let draftPasteCount = 0
  let inputLocated = false
  let draftWritten = false
  let contentVerified = false
  let verificationFailed = false
  let activeWindow: WindowDescriptor | null = null
  let clipboardRoundtripVerified = false
  let verificationMethod = 'unavailable'
  let verificationErrorCode: string | undefined
  const expectedDiagnostics = measureText(draftText)
  let actualTextLength = expectedDiagnostics.textLengthUtf16
  let actualCodePointCount = expectedDiagnostics.codePointCount
  let actualDigest = expectedDiagnostics.digest
  let actualLineCount = expectedDiagnostics.lineCount

  try {
    stage = 'activating_window'
    const targetWindow = await findTargetWindow()
    if (!targetWindow.ok) {
      status = 'blocked'
      errorCode = targetWindow.errorCode
      return result()
    }
    const activated = await activateTargetWindow(targetWindow.window)
    if (!activated.ok) {
      status = 'blocked'
      errorCode = activated.errorCode ?? 'WINDOW_ACTIVATION_FAILED'
      return result()
    }
    activeWindow = activated.window ?? targetWindow.window

    stage = 'opening_search'
    searchShortcutCount += 1
    await deps.input.hotkey(['Control', 'F'])
    await sleep(400)

    stage = 'pasting_conversation_name'
    await deps.clipboard.writeDraftText(conversationName)
    conversationPasteCount += 1
    await deps.input.hotkey(['Control', 'V'])
    await sleep(400)

    stage = 'confirming_conversation'
    conversationConfirmEnterCount += 1
    await deps.input.hotkey(['Enter'])
    await sleep(1000)

    stage = 'pasting_draft'
    await deps.clipboard.writeDraftText(draftText)
    const clipboardRoundtripText = deps.clipboard.systemText()
    const clipboardDiagnostics = measureText(clipboardRoundtripText)
    actualTextLength = clipboardDiagnostics.textLengthUtf16
    actualCodePointCount = clipboardDiagnostics.codePointCount
    actualDigest = clipboardDiagnostics.digest
    actualLineCount = clipboardDiagnostics.lineCount
    clipboardRoundtripVerified = textsEquivalent(draftText, clipboardRoundtripText)
    if (!clipboardRoundtripVerified) {
      status = 'interrupted'
      stage = 'clipboard_roundtrip_mismatch'
      errorCode = 'CLIPBOARD_ROUNDTRIP_MISMATCH'
      verificationFailed = true
      verificationMethod = 'clipboard_roundtrip'
      verificationErrorCode = errorCode
      return result()
    }

    draftPasteCount += 1
    await deps.input.hotkey(['Control', 'V'])

    stage = 'verifying_paste'
    const verification = await (deps.verifyPasteContent ?? defaultVerifyPasteContent)({
      conversationName,
      draftText,
      window: activeWindow,
    })
    inputLocated = verification.inputLocated
    draftWritten = verification.draftWritten
    contentVerified = verification.contentVerified
    verificationFailed = !verification.ok
    verificationMethod = verification.verificationMethod ?? verificationMethod
    verificationErrorCode = verification.verificationErrorCode ?? verification.errorCode
    actualTextLength = verification.actualTextLength ?? actualTextLength
    actualCodePointCount = verification.actualCodePointCount ?? actualCodePointCount
    actualDigest = verification.actualDigest ?? actualDigest
    actualLineCount = verification.actualLineCount ?? actualLineCount
    if (!verification.ok) {
      status = 'interrupted'
      stage = verification.runtimeState ?? 'paste_verification_failed'
      errorCode = verification.errorCode ?? 'PASTE_VERIFICATION_FAILED'
      return result()
    }

    stage = 'restoring_clipboard'
  } catch (error) {
    status = 'failed'
    errorCode = error instanceof Error && error.message ? error.message : 'PASTE_FAILED'
  } finally {
    try {
      await deps.clipboard.restore(clipboardState.snapshot)
    } catch {
      clipboardRestoreFailed = true
    }
  }

  if (status === 'succeeded' && clipboardRestoreFailed) {
    status = 'succeeded_with_warning'
    errorCode = 'CLIPBOARD_RESTORE_MISMATCH'
  }
  return result()

  function result() {
    return buildResult(request, status, status === 'succeeded' || status === 'succeeded_with_warning' ? 'pasted_to_input' : stage, errorCode, {
      clipboardRestoreFailed,
      searchShortcutCount,
      conversationPasteCount,
      conversationConfirmEnterCount,
      draftPasteCount,
      inputLocated,
      draftWritten,
      contentVerified,
      verificationFailed,
      clipboardRoundtripVerified,
      verificationMethod,
      verificationErrorCode,
      expectedTextLength: expectedDiagnostics.textLengthUtf16,
      actualTextLength,
      expectedCodePointCount: expectedDiagnostics.codePointCount,
      actualCodePointCount,
      expectedDigest: expectedDiagnostics.digest,
      actualDigest,
      expectedLineCount: expectedDiagnostics.lineCount,
      actualLineCount,
      expectedCrCount: expectedDiagnostics.crCount,
      expectedLfCount: expectedDiagnostics.lfCount,
    })
  }
}

function buildResult(
  request: RuntimeTaskRequest,
  status: string,
  stage: string,
  errorCode?: string,
  extra: Record<string, unknown> = {},
) {
  return {
    status,
    stage,
    ...(errorCode ? { errorCode } : {}),
    messageSent: false,
    clipboardRestoreFailed: false,
    searchShortcutCount: 0,
    conversationPasteCount: 0,
    conversationConfirmEnterCount: 0,
    draftPasteCount: 0,
    inputLocated: false,
    draftWritten: false,
    contentVerified: false,
    verificationFailed: false,
    clipboardRoundtripVerified: false,
    verificationMethod: 'unavailable',
    verificationErrorCode: undefined,
    expectedTextLength: 0,
    actualTextLength: 0,
    expectedCodePointCount: 0,
    actualCodePointCount: 0,
    expectedDigest: '',
    actualDigest: '',
    expectedLineCount: 0,
    actualLineCount: 0,
    expectedCrCount: 0,
    expectedLfCount: 0,
    sendKeyCount: 0,
    idempotencyKey: request.idempotencyKey,
    requestDigest: request.requestDigest,
    ...extra,
  }
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function defaultVerifyPasteContent(): Promise<PasteVerificationResult> {
  return {
    ok: false,
    inputLocated: false,
    draftWritten: false,
    contentVerified: false,
    runtimeState: 'paste_verification_unavailable',
    errorCode: 'PASTE_VERIFICATION_UNAVAILABLE',
    verificationMethod: 'unavailable',
    verificationErrorCode: 'PASTE_VERIFICATION_UNAVAILABLE',
  }
}

function normalizeNewlines(text: string): string {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
}

function textsEquivalent(expected: string, actual: string): boolean {
  return normalizeNewlines(expected) === normalizeNewlines(actual)
}

function measureText(text: string): TextDiagnostics {
  const normalized = normalizeNewlines(text)
  const crMatches = text.match(/\r/g)
  const lfMatches = text.match(/\n/g)
  return {
    textLengthUtf16: text.length,
    codePointCount: [...text].length,
    digest: createHash('sha256').update(text, 'utf8').digest('hex'),
    lineCount: normalized.length === 0 ? 1 : normalized.split('\n').length,
    crCount: crMatches?.length ?? 0,
    lfCount: lfMatches?.length ?? 0,
  }
}
