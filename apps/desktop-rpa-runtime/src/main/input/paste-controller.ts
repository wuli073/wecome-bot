import { createHash } from 'node:crypto'
import { promises as fs } from 'node:fs'
import path from 'node:path'
import type { RuntimeAttachmentPayload, RuntimeTaskRequest } from '../domain/task-types'
import type { WindowDescriptor } from '../domain/window-types'
import { activateWindow } from '../window/window-activator'
import {
  findUniqueVisibleWxWorkMainWindow,
  matchesWxWorkWindow,
} from '../window/window-finder'
import { ClipboardController } from './clipboard-controller'
import {
  computeAttachmentPostPasteDelayMs,
  type FileClipboardController,
} from './file-clipboard-controller'
import type { InputDriver } from './mouse-controller'
import type { WxWorkWindowSelectionDiagnostics } from '../window/window-finder'

type TargetWindowResult =
  | { ok: true; window: WindowDescriptor; diagnostics?: WxWorkWindowSelectionDiagnostics }
  | {
      ok: false
      errorCode: 'TARGET_WINDOW_NOT_FOUND' | 'TARGET_WINDOW_AMBIGUOUS'
      candidates: WindowDescriptor[]
      diagnostics?: WxWorkWindowSelectionDiagnostics
    }

export interface PasteTaskDeps {
  clipboard: ClipboardController
  input: InputDriver
  sleep?: (ms: number) => Promise<void>
  findTargetWindow?: () => Promise<TargetWindowResult>
  activateTargetWindow?: (window: WindowDescriptor) => Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }>
  fileClipboard?: FileClipboardController
  getActiveWindow?: () => Promise<WindowDescriptor | null>
  isCancelled?: () => boolean
}

interface TextDiagnostics {
  textLengthUtf16: number
  codePointCount: number
  digest: string
  lineCount: number
  crCount: number
  lfCount: number
}

export async function runPasteOnlyTask(request: RuntimeTaskRequest, deps: PasteTaskDeps): Promise<Record<string, unknown>> {
  const conversationName = String(request.conversationName ?? '').trim()
  const draftText = String(request.draftText ?? '')
  if (!conversationName) return buildResult(request, 'blocked', 'queued', 'CONVERSATION_NAME_REQUIRED')
  if (!draftText.trim()) return buildResult(request, 'blocked', 'queued', 'DRAFT_TEXT_REQUIRED')
  const attachments = Array.isArray(request.attachments) ? request.attachments : []
  let resolvedAttachments: RuntimeAttachmentPayload[] = []
  try {
    resolvedAttachments = await verifyAttachmentPayloads(request.attachmentRoot, attachments)
  } catch (error) {
    return buildResult(
      request,
      'failed',
      'validating_attachments',
      error instanceof Error ? error.message : 'ATTACHMENT_VALIDATION_FAILED',
    )
  }

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
  let attachmentsPrepared = false
  let attachmentPasteRequested = false
  let attachmentsVerified = false
  let successfulStage = 'text_pasted_unverified'
  let warning = 'PASTE_RESULT_NOT_VERIFIED'
  let observationAvailable = false
  const expectedDiagnostics = measureText(draftText)
  let actualTextLength: number | null = null
  let actualCodePointCount: number | null = null
  let actualDigest: string | null = null
  let actualLineCount: number | null = null
  let actualCrCount: number | null = null
  let actualLfCount: number | null = null
  let targetWindowDiagnostics: WxWorkWindowSelectionDiagnostics | undefined
  const getActiveWindow = deps.getActiveWindow
  const isCancelled = deps.isCancelled ?? (() => false)

  try {
    throwIfCancelled(isCancelled)
    stage = 'finding_window'
    const targetWindow = await findTargetWindow()
    targetWindowDiagnostics = targetWindow.diagnostics
    if (!targetWindow.ok) {
      status = 'blocked'
      errorCode = targetWindow.errorCode
      return result()
    }

    stage = 'activating_window'
    const activated = await activateTargetWindow(targetWindow.window)
    if (!activated.ok) {
      status = 'blocked'
      errorCode = activated.errorCode ?? 'WINDOW_ACTIVATION_FAILED'
      return result()
    }
    activeWindow = activated.window ?? targetWindow.window
    await sleep(300)
    throwIfCancelled(isCancelled)
    await ensureWindowStillActive(getActiveWindow, activeWindow, 'WINDOW_ACTIVATION_FAILED')

    stage = 'activating_search'
    searchShortcutCount += 1
    await deps.input.hotkey(['Control', 'F'])
    await sleep(200)
    throwIfCancelled(isCancelled)
    await ensureWindowStillActive(getActiveWindow, activeWindow, 'SEARCH_ACTIVATION_FAILED')
    throwIfCancelled(isCancelled)
    await deps.input.hotkey(['Control', 'A'])

    stage = 'pasting_conversation_name'
    throwIfCancelled(isCancelled)
    await deps.clipboard.writeDraftText(conversationName)
    throwIfCancelled(isCancelled)
    conversationPasteCount += 1
    await deps.input.hotkey(['Control', 'V'])
    await sleep(300)
    throwIfCancelled(isCancelled)
    await ensureWindowStillActive(getActiveWindow, activeWindow, 'CONVERSATION_NAME_PASTE_FAILED')

    stage = 'confirming_search_result'
    throwIfCancelled(isCancelled)
    conversationConfirmEnterCount += 1
    await deps.input.hotkey(['Enter'])

    stage = 'waiting_for_conversation_open'
    await sleep(600)
    throwIfCancelled(isCancelled)
    await ensureWindowStillActive(getActiveWindow, activeWindow, 'SEARCH_RESULT_CONFIRM_FAILED')

    stage = 'pasting_text'
    throwIfCancelled(isCancelled)
    await deps.clipboard.writeDraftText(draftText)
    throwIfCancelled(isCancelled)
    draftPasteCount += 1
    await deps.input.hotkey(['Control', 'V'])
    draftWritten = true
    status = 'succeeded_with_warning'
    successfulStage = 'text_pasted_unverified'

    if (attachments.length > 0) {
      stage = 'pasting_attachments'
      throwIfCancelled(isCancelled)
      if (!deps.fileClipboard) {
        status = 'failed'
        errorCode = 'FILE_CLIPBOARD_HELPER_FAILED'
        return result()
      }
      throwIfCancelled(isCancelled)
      await deps.fileClipboard.writeFiles(resolvedAttachments)
      attachmentsPrepared = true
      const reactivated = await activateTargetWindow(activeWindow)
      if (!reactivated.ok) {
        status = 'failed'
        errorCode = 'TARGET_WINDOW_LOST_BEFORE_ATTACHMENT_PASTE'
        return result()
      }
      activeWindow = reactivated.window ?? activeWindow
      await sleep(200)
      throwIfCancelled(isCancelled)
      await ensureAttachmentForeground(getActiveWindow, activeWindow)
      throwIfCancelled(isCancelled)
      await deps.input.hotkey(['Control', 'V'])
      attachmentPasteRequested = true
      await sleep(computeAttachmentPostPasteDelayMs(sumAttachmentBytes(resolvedAttachments)))
      status = 'succeeded_with_warning'
      stage = 'attachments_pasted_unverified'
      successfulStage = stage
      attachmentsVerified = false
    }

    stage = 'restoring_clipboard'
  } catch (error) {
    errorCode = classifyPasteOnlyFailure(stage, error)
    status = errorCode === 'TASK_CANCELLED' ? 'cancelled' : 'failed'
  } finally {
    try {
      await deps.clipboard.restore(clipboardState.snapshot)
    } catch {
      clipboardRestoreFailed = true
    }
  }

  if (status === 'succeeded_with_warning' && clipboardRestoreFailed) {
    status = 'succeeded_with_warning'
    errorCode = 'CLIPBOARD_RESTORE_MISMATCH'
  }
  return result()

  function result() {
    const finalStage = status === 'succeeded_with_warning' ? successfulStage : stage
    return buildResult(request, status, finalStage, errorCode, {
      warning: status === 'succeeded_with_warning' ? warning : undefined,
      clipboardRestoreFailed,
      searchShortcutCount,
      conversationPasteCount,
      conversationConfirmEnterCount,
      draftPasteCount,
      inputLocated,
      draftWritten,
      contentVerified,
      verificationFailed,
      sendTriggered: false,
      sendAuthorized: false,
      attachmentsPrepared,
      attachmentPasteRequested,
      attachmentsVerified,
      attachmentCount: attachments.length,
      observationAvailable,
      windowTitle: activeWindow?.title ?? targetWindowDiagnostics?.selectedWindow?.title ?? undefined,
      expectedTextLength: expectedDiagnostics.textLengthUtf16,
      actualTextLength,
      expectedCodePointCount: expectedDiagnostics.codePointCount,
      actualCodePointCount,
      expectedDigest: expectedDiagnostics.digest,
      actualDigest,
      expectedLineCount: expectedDiagnostics.lineCount,
      actualLineCount,
      expectedCrCount: expectedDiagnostics.crCount,
      actualCrCount,
      expectedLfCount: expectedDiagnostics.lfCount,
      actualLfCount,
      ...(targetWindowDiagnostics ? targetWindowDiagnostics : {}),
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
    sendTriggered: false,
    sendAuthorized: false,
    attachmentsPrepared: false,
    attachmentPasteRequested: false,
    attachmentsVerified: false,
    attachmentCount: Array.isArray(request.attachments) ? request.attachments.length : 0,
    warning: undefined,
    observationAvailable: false,
    expectedTextLength: 0,
    actualTextLength: null,
    expectedCodePointCount: 0,
    actualCodePointCount: null,
    expectedDigest: '',
    actualDigest: null,
    expectedLineCount: 0,
    actualLineCount: null,
    expectedCrCount: 0,
    actualCrCount: null,
    expectedLfCount: 0,
    actualLfCount: null,
    sendKeyCount: 0,
    idempotencyKey: request.idempotencyKey,
    requestDigest: request.requestDigest,
    ...extra,
  }
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function normalizeNewlines(text: string): string {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
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

async function verifyAttachmentPayloads(
  attachmentRoot: string | undefined,
  attachments: RuntimeTaskRequest['attachments'],
): Promise<RuntimeAttachmentPayload[]> {
  if ((attachments ?? []).length === 0) {
    return []
  }
  if ((attachments ?? []).length > 9) throw new Error('ATTACHMENT_COUNT_EXCEEDED')
  const rootText = String(attachmentRoot || '').trim()
  if (!rootText) throw new Error('ATTACHMENT_PATH_OUTSIDE_ROOT')
  let canonicalRoot: string
  try {
    canonicalRoot = await fs.realpath(rootText)
  } catch {
    throw new Error('ATTACHMENT_PATH_OUTSIDE_ROOT')
  }

  const verified: RuntimeAttachmentPayload[] = []
  let totalBytes = 0
  for (const attachment of attachments ?? []) {
    const relativePath = String(attachment.relativePath || '').trim()
    if (!relativePath) throw new Error('ATTACHMENT_FILE_MISSING')
    const filename = String(attachment.filename || '').trim()
    if (!filename) throw new Error('ATTACHMENT_FILE_MISSING')
    const candidatePath = path.resolve(canonicalRoot, relativePath)
    let canonicalFile: string
    try {
      canonicalFile = await fs.realpath(candidatePath)
    } catch {
      throw new Error('ATTACHMENT_FILE_MISSING')
    }
    const relative = path.relative(canonicalRoot, canonicalFile)
    if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('ATTACHMENT_PATH_OUTSIDE_ROOT')
    let stat
    try {
      stat = await fs.stat(canonicalFile)
    } catch {
      throw new Error('ATTACHMENT_FILE_MISSING')
    }
    if (!stat.isFile()) throw new Error('ATTACHMENT_FILE_MISSING')
    if (Number(attachment.size || 0) !== stat.size) throw new Error('ATTACHMENT_HASH_MISMATCH')
    totalBytes += stat.size
    if (totalBytes > 200 * 1024 * 1024) throw new Error('ATTACHMENT_TOTAL_TOO_LARGE')
    const expectedSha256 = String(attachment.sha256 || '').trim().toLowerCase()
    if (!expectedSha256) throw new Error('ATTACHMENT_HASH_MISMATCH')
    const actualSha256 = createHash('sha256').update(await fs.readFile(canonicalFile)).digest('hex')
    if (actualSha256 !== expectedSha256) throw new Error('ATTACHMENT_HASH_MISMATCH')
    verified.push({
      ...attachment,
      resolvedPath: canonicalFile,
    })
  }
  return verified
}

async function ensureWindowStillActive(
  getActiveWindow: (() => Promise<WindowDescriptor | null>) | undefined,
  targetWindow: WindowDescriptor,
  errorCode: string,
): Promise<void> {
  if (!getActiveWindow) return
  const activeWindow = await getActiveWindow().catch(() => null)
  if (activeWindow && !matchesTargetWindow(activeWindow, targetWindow)) {
    throw new Error(errorCode)
  }
}

function matchesTargetWindow(
  activeWindow: WindowDescriptor | null | undefined,
  targetWindow: WindowDescriptor,
): boolean {
  if (!activeWindow) return false
  return String(activeWindow.windowId) === String(targetWindow.windowId)
    && Number(activeWindow.processId) === Number(targetWindow.processId)
}

async function ensureAttachmentForeground(
  getActiveWindow: (() => Promise<WindowDescriptor | null>) | undefined,
  targetWindow: WindowDescriptor,
): Promise<void> {
  if (!getActiveWindow) return
  const foregroundWindow = await getActiveWindow().catch(() => null)
  if (!matchesAttachmentForeground(foregroundWindow, targetWindow)) {
    throw new Error('TARGET_WINDOW_LOST_BEFORE_ATTACHMENT_PASTE')
  }
}

function matchesAttachmentForeground(
  activeWindow: WindowDescriptor | null | undefined,
  targetWindow: WindowDescriptor,
): boolean {
  if (!activeWindow || !matchesWxWorkWindow(activeWindow)) {
    return false
  }
  const activeRoot = String(activeWindow.rootWindowId || activeWindow.windowId)
  const targetRoot = String(targetWindow.rootWindowId || targetWindow.windowId)
  if (activeRoot && targetRoot && activeRoot === targetRoot) {
    return true
  }
  return normalizeExecutable(activeWindow.executablePath) === normalizeExecutable(targetWindow.executablePath)
    && normalizeProcess(activeWindow.processName) === normalizeProcess(targetWindow.processName)
}

function normalizeExecutable(value: string | null | undefined): string {
  return String(value || '').trim().replace(/\\/g, '/').toLowerCase()
}

function normalizeProcess(value: string | null | undefined): string {
  return String(value || '').trim().toLowerCase()
}

function sumAttachmentBytes(files: RuntimeAttachmentPayload[]): number {
  return files.reduce((total, item) => total + Math.max(0, Number(item.size || 0)), 0)
}

function classifyPasteOnlyFailure(stage: string, error: unknown): string {
  const raw = error instanceof Error && error.message ? error.message : ''
  if (raw) {
    return raw
  }
  if (stage === 'activating_search') return 'SEARCH_ACTIVATION_FAILED'
  if (stage === 'pasting_conversation_name') return 'CONVERSATION_NAME_PASTE_FAILED'
  if (stage === 'confirming_search_result' || stage === 'waiting_for_conversation_open') return 'SEARCH_RESULT_CONFIRM_FAILED'
  if (stage === 'pasting_text') return 'TEXT_PASTE_FAILED'
  if (stage === 'pasting_attachments') return 'ATTACHMENT_PASTE_FAILED'
  return 'PASTE_FAILED'
}

function throwIfCancelled(isCancelled: () => boolean): void {
  if (isCancelled()) {
    throw new Error('TASK_CANCELLED')
  }
}
