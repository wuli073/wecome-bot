import { createHash } from 'node:crypto'
import { promises as fs } from 'node:fs'
import path from 'node:path'
import type { RuntimeAttachmentPayload, RuntimeTaskRequest } from '../domain/task-types'
import type { WindowDescriptor } from '../domain/window-types'
import { activateWindow } from '../window/window-activator'
import {
  findUniqueVisibleWxWorkMainWindow,
  matchesWxWorkWindow,
  type WxWorkWindowSelectionDiagnostics,
} from '../window/window-finder'
import { ClipboardController } from './clipboard-controller'
import {
  computeAttachmentPostPasteDelayMs,
  type FileClipboardController,
} from './file-clipboard-controller'
import type { InputDriver } from './mouse-controller'
import type { PasteVerificationProvider } from './paste-verification'
import { normalizeConversationName, verifyConversationName } from '../vision/session-verifier'

export const CONVERSATION_OPEN_DELAY_MS = 800
export const PASTE_SETTLE_DELAY_MS = 150

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
  pasteVerificationProvider?: PasteVerificationProvider
}

export interface PrepareDraftInputResult {
  activeWindow: WindowDescriptor | null
  runtimeResult: Record<string, unknown>
}

interface TextDiagnostics {
  textLengthUtf16: number
  codePointCount: number
  digest: string
  lineCount: number
  crCount: number
  lfCount: number
}

interface ConversationResolutionResult {
  ok: boolean
  errorCode?: string
  errorMessage?: string
  stage?: string
  evidence?: Record<string, unknown>
}

export async function runPasteOnlyTask(request: RuntimeTaskRequest, deps: PasteTaskDeps): Promise<Record<string, unknown>> {
  const prepared = await prepareDraftInput(request, deps)
  const result = { ...prepared.runtimeResult }
  if (String(result.status) !== 'prepared') {
    return result
  }

  const attachmentCount = Number(result.attachmentCount ?? 0)
  return {
    ...result,
    status: attachmentCount > 0 || Boolean(result.clipboardRestoreFailed) ? 'succeeded_with_warning' : 'succeeded',
    stage: attachmentCount > 0 ? 'attachments_pasted_unverified' : 'text_pasted_unverified',
    terminalConfirmed: true,
    terminal_confirmed: true,
    enterDispatched: false,
    enter_dispatched: false,
    messageSent: false,
    message_sent: false,
    retryAllowed: false,
    retry_allowed: false,
    resultText: attachmentCount > 0 ? '\u5df2\u7c98\u8d34\u9644\u4ef6\uff0c\u672a\u53d1\u9001' : '\u5df2\u7c98\u8d34\uff0c\u672a\u53d1\u9001',
    result_text: attachmentCount > 0 ? '\u5df2\u7c98\u8d34\u9644\u4ef6\uff0c\u672a\u53d1\u9001' : '\u5df2\u7c98\u8d34\uff0c\u672a\u53d1\u9001',
    sendTriggered: false,
    sendAuthorized: false,
  }
}

export async function prepareDraftInput(
  request: RuntimeTaskRequest,
  deps: PasteTaskDeps,
): Promise<PrepareDraftInputResult> {
  const conversationName = String(request.conversationName ?? '').trim()
  const draftText = String(request.draftText ?? request.messageText ?? '')
  if (!conversationName) {
    return { activeWindow: null, runtimeResult: buildResult(request, 'blocked', 'queued', 'CONVERSATION_NAME_REQUIRED') }
  }
  if (!draftText.trim()) {
    return { activeWindow: null, runtimeResult: buildResult(request, 'blocked', 'queued', 'DRAFT_TEXT_REQUIRED') }
  }

  const attachments = Array.isArray(request.attachments) ? request.attachments : []
  let resolvedAttachments: RuntimeAttachmentPayload[] = []
  try {
    resolvedAttachments = await verifyAttachmentPayloads(request.attachmentRoot, attachments)
  } catch (error) {
    return {
      activeWindow: null,
      runtimeResult: buildResult(
        request,
        'failed',
        'validating_attachments',
        error instanceof Error ? error.message : 'ATTACHMENT_VALIDATION_FAILED',
      ),
    }
  }

  const clipboardState = deps.clipboard.inspectRestorable()
  if (!clipboardState.ok) {
    return {
      activeWindow: null,
      runtimeResult: buildResult(request, 'blocked', 'queued', clipboardState.errorCode, undefined, {
        unsupportedFormats: clipboardState.unsupportedFormats,
      }),
    }
  }

  const sleep = deps.sleep ?? defaultSleep
  const findTargetWindow = deps.findTargetWindow ?? findUniqueVisibleWxWorkMainWindow
  const activateTargetWindow = deps.activateTargetWindow ?? activateWindow
  const getActiveWindow = deps.getActiveWindow
  const isCancelled = deps.isCancelled ?? (() => false)
  let status: 'prepared' | 'blocked' | 'failed' | 'cancelled' = 'prepared'
  let stage = 'queued'
  let errorCode: string | undefined
  let errorMessage: string | undefined
  let clipboardRestoreFailed = false
  let searchShortcutCount = 0
  let conversationInputCount = 0
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
  let attachmentsVerified = attachments.length === 0
  let successfulStage = 'text_pasted_unverified'
  let warning: string | undefined = 'PASTE_RESULT_NOT_VERIFIED'
  let observationAvailable = false
  const expectedDiagnostics = measureText(draftText)
  let actualTextLength: number | null = null
  let actualCodePointCount: number | null = null
  let actualDigest: string | null = null
  let actualLineCount: number | null = null
  let actualCrCount: number | null = null
  let actualLfCount: number | null = null
  let targetWindowDiagnostics: WxWorkWindowSelectionDiagnostics | undefined
  let verificationMethod: string | undefined
  const evidence: Array<Record<string, unknown>> = []
  const requireLiveConversationResolution = request.action === 'send_draft' || request.action === 'send_message'

  try {
    throwIfCancelled(isCancelled)
    stage = 'finding_window'
    const targetWindow = await findTargetWindow()
    targetWindowDiagnostics = targetWindow.diagnostics
    if (!targetWindow.ok) {
      status = 'blocked'
      errorCode = targetWindow.errorCode
      return { activeWindow, runtimeResult: result() }
    }

    stage = 'activating_window'
    const activated = await activateTargetWindow(targetWindow.window)
    if (!activated.ok) {
      status = 'blocked'
      errorCode = activated.errorCode ?? 'WINDOW_ACTIVATION_FAILED'
      return { activeWindow, runtimeResult: result() }
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

    stage = 'typing_conversation_name'
    throwIfCancelled(isCancelled)
    if (!deps.input.typeText) {
      throw new Error('SEARCH_TEXT_INPUT_UNAVAILABLE')
    }
    await deps.input.typeText(conversationName)
    conversationInputCount += 1
    await sleep(300)
    throwIfCancelled(isCancelled)
    await ensureWindowStillActive(getActiveWindow, activeWindow, 'CONVERSATION_NAME_INPUT_FAILED')

    if (requireLiveConversationResolution) {
      const searchResolution = await resolveConversationBySearchResult({
        conversationName,
        draftText,
        activeWindow: activeWindow as WindowDescriptor,
        provider: deps.pasteVerificationProvider,
      })
      if (searchResolution.evidence) {
        evidence.push(searchResolution.evidence)
      }
      if (!searchResolution.ok) {
        status = 'failed'
        stage = searchResolution.stage ?? 'resolving_conversation'
        errorCode = searchResolution.errorCode ?? 'SEARCH_RESULT_CONFIRM_FAILED'
        errorMessage = searchResolution.errorMessage ?? errorCode
        return { activeWindow, runtimeResult: result() }
      }
    }

    stage = 'confirming_search_result'
    throwIfCancelled(isCancelled)
    conversationConfirmEnterCount += 1
    await deps.input.hotkey(['Enter'])

    stage = 'waiting_for_conversation_open'
    await sleep(CONVERSATION_OPEN_DELAY_MS)
    throwIfCancelled(isCancelled)
    await ensureWindowStillActive(getActiveWindow, activeWindow, 'SEARCH_RESULT_CONFIRM_FAILED')

    if (requireLiveConversationResolution) {
      const openedConversationConfirmation = await confirmOpenedConversation({
        conversationName,
        draftText,
        activeWindow: activeWindow as WindowDescriptor,
        provider: deps.pasteVerificationProvider,
      })
      if (openedConversationConfirmation.evidence) {
        evidence.push(openedConversationConfirmation.evidence)
      }
      if (!openedConversationConfirmation.ok) {
        status = 'failed'
        stage = openedConversationConfirmation.stage ?? 'resolving_conversation'
        errorCode = openedConversationConfirmation.errorCode ?? 'SEARCH_RESULT_CONFIRM_FAILED'
        errorMessage = openedConversationConfirmation.errorMessage ?? errorCode
        return { activeWindow, runtimeResult: result() }
      }
    }

    stage = 'pasting_text'
    throwIfCancelled(isCancelled)
    await deps.clipboard.writeDraftText(draftText)
    throwIfCancelled(isCancelled)
    draftPasteCount += 1
    await deps.input.hotkey(['Control', 'V'])
    draftWritten = true
    successfulStage = 'text_pasted_unverified'
    warning = undefined

    if (attachments.length > 0) {
      stage = 'pasting_attachments'
      throwIfCancelled(isCancelled)
      if (!deps.fileClipboard) {
        status = 'failed'
        errorCode = 'FILE_CLIPBOARD_HELPER_FAILED'
        errorMessage = errorCode
        return { activeWindow, runtimeResult: result() }
      }
      throwIfCancelled(isCancelled)
      await deps.fileClipboard.writeFiles(resolvedAttachments)
      attachmentsPrepared = true
      const reactivated = await activateTargetWindow(activeWindow as WindowDescriptor)
      if (!reactivated.ok) {
        status = 'failed'
        errorCode = 'TARGET_WINDOW_LOST_BEFORE_ATTACHMENT_PASTE'
        errorMessage = errorCode
        return { activeWindow, runtimeResult: result() }
      }
      activeWindow = reactivated.window ?? activeWindow
      await sleep(200)
      throwIfCancelled(isCancelled)
      await ensureAttachmentForeground(getActiveWindow, activeWindow)
      throwIfCancelled(isCancelled)
      await deps.input.hotkey(['Control', 'V'])
      attachmentPasteRequested = true
      await sleep(computeAttachmentPostPasteDelayMs(sumAttachmentBytes(resolvedAttachments)))
      attachmentsVerified = false
      successfulStage = 'attachments_pasted_unverified'
      warning = 'PASTE_RESULT_NOT_VERIFIED'
    }

    stage = 'restoring_clipboard'
  } catch (error) {
    errorCode = classifyPasteOnlyFailure(stage, error)
    errorMessage = errorCode
    status = errorCode === 'TASK_CANCELLED' ? 'cancelled' : 'failed'
  } finally {
    try {
      await deps.clipboard.restore(clipboardState.snapshot)
    } catch {
      clipboardRestoreFailed = true
    }
  }

  if (status === 'prepared' && clipboardRestoreFailed) {
    errorCode = 'CLIPBOARD_RESTORE_MISMATCH'
    errorMessage = 'CLIPBOARD_RESTORE_MISMATCH'
  }

  evidence.push({
    phase: 'prepare',
    ok: status === 'prepared',
    stage: status === 'prepared' ? successfulStage : stage,
    error_code: errorCode,
  })
  return { activeWindow, runtimeResult: result() }

  function result() {
    const finalStage = status === 'prepared' ? successfulStage : stage
    return buildResult(request, status, finalStage, errorCode, errorMessage, {
      warning: status === 'prepared' ? warning : undefined,
      clipboardRestoreFailed,
      searchShortcutCount,
      conversationInputCount,
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
      verificationMethod,
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
      evidence,
      ...(targetWindowDiagnostics ? targetWindowDiagnostics : {}),
    })
  }
}

function buildResult(
  request: RuntimeTaskRequest,
  status: string,
  stage: string,
  errorCode?: string,
  errorMessage?: string,
  extra: Record<string, unknown> = {},
) {
  return {
    status,
    stage,
    ...(errorCode ? { errorCode, error_code: errorCode } : {}),
    ...(errorMessage ? { errorMessage, error_message: errorMessage } : {}),
    messageSent: false,
    clipboardRestoreFailed: false,
    searchShortcutCount: 0,
    conversationInputCount: 0,
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
    send_key_count: 0,
    enterDispatched: false,
    enter_dispatched: false,
    message_sent: false,
    terminalConfirmed: true,
    terminal_confirmed: true,
    retryAllowed: false,
    retry_allowed: false,
    resultText: undefined,
    result_text: undefined,
    idempotencyKey: request.idempotencyKey,
    requestDigest: request.requestDigest,
    evidence: [],
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
  if (stage === 'typing_conversation_name') return 'CONVERSATION_NAME_INPUT_FAILED'
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

async function resolveConversationBySearchResult(args: {
  conversationName: string
  draftText: string
  activeWindow: WindowDescriptor
  provider?: PasteVerificationProvider
}): Promise<ConversationResolutionResult> {
  const provider = args.provider
  if (!provider?.verifyInputContent || provider.getCapability?.().available === false) {
    return { ok: true }
  }

  const observation = await provider.verifyInputContent({
    conversationName: args.conversationName,
    draftText: args.draftText,
    window: args.activeWindow,
    phase: 'before_paste',
  })
  if (!observation.ok) {
    return {
      ok: false,
      errorCode: observation.errorCode ?? observation.verificationErrorCode ?? 'SEARCH_RESULT_CONFIRM_FAILED',
      errorMessage: observation.sanitizedMessage ?? observation.errorCode ?? observation.verificationErrorCode,
      stage: 'resolving_conversation',
      evidence: {
        step: 'resolve_failed',
        ok: false,
        error_code: observation.errorCode ?? observation.verificationErrorCode ?? 'SEARCH_RESULT_CONFIRM_FAILED',
      },
    }
  }

  return buildConversationResolutionResult(
    args.conversationName,
    observation.conversationCandidates,
    observation.observedConversation,
  )
}

async function confirmOpenedConversation(args: {
  conversationName: string
  draftText: string
  activeWindow: WindowDescriptor
  provider?: PasteVerificationProvider
}): Promise<ConversationResolutionResult> {
  const provider = args.provider
  if (!provider?.verifyInputContent || provider.getCapability?.().available === false) {
    return { ok: true }
  }

  const observation = await provider.verifyInputContent({
    conversationName: args.conversationName,
    draftText: args.draftText,
    window: args.activeWindow,
    phase: 'before_paste',
  })
  if (!observation.ok) {
    return {
      ok: false,
      errorCode: observation.errorCode ?? observation.verificationErrorCode ?? 'SEARCH_RESULT_CONFIRM_FAILED',
      errorMessage: observation.sanitizedMessage ?? observation.errorCode ?? observation.verificationErrorCode,
      stage: 'resolving_conversation',
      evidence: {
        step: 'resolve_failed',
        ok: false,
        error_code: observation.errorCode ?? observation.verificationErrorCode ?? 'SEARCH_RESULT_CONFIRM_FAILED',
      },
    }
  }

  const observedConversation = normalizeConversationName(String(observation.observedConversation ?? ''))
  if (!observedConversation) {
    return {
      ok: true,
      evidence: {
        step: 'resolve_succeeded',
        ok: true,
        observed_conversation: null,
      },
    }
  }

  const verification = verifyConversationName(args.conversationName, observedConversation)
  if (!verification.ok) {
    return {
      ok: false,
      errorCode: 'TARGET_GROUP_NOT_FOUND',
      errorMessage: `未找到目标群聊“${args.conversationName}”，请确认企业微信中存在完全同名的群聊。`,
      stage: 'resolve_not_found',
      evidence: {
        step: 'resolve_not_found',
        ok: false,
        observed_conversation: observedConversation,
        normalized_expected: verification.normalizedExpected,
        normalized_observed: verification.normalizedObserved,
      },
    }
  }

  return {
    ok: true,
    evidence: {
      step: 'resolve_succeeded',
      ok: true,
      observed_conversation: observedConversation,
      normalized_expected: verification.normalizedExpected,
      normalized_observed: verification.normalizedObserved,
    },
  }
}

function buildConversationResolutionResult(
  conversationName: string,
  candidates: string[] | undefined,
  observedConversation: string | null | undefined,
): ConversationResolutionResult {
  const normalizedTarget = normalizeConversationName(conversationName)
  const rawCandidates = Array.isArray(candidates)
    ? candidates
      .filter((candidate): candidate is string => typeof candidate === 'string')
      .map((candidate) => candidate.trim())
      .filter((candidate) => candidate.length > 0)
    : []
  const normalizedCandidates = rawCandidates
    .map((candidate) => normalizeConversationName(candidate))
    .filter((candidate) => candidate.length > 0)
  const normalizedObservedConversation = normalizeConversationName(String(observedConversation ?? ''))
  const rawExactMatches = normalizedCandidates.filter((candidate) => candidate === normalizedTarget)
  const effectiveExactMatchCount = Math.max(
    0,
    rawExactMatches.length - (normalizedObservedConversation === normalizedTarget && rawExactMatches.length > 0 ? 1 : 0),
  )
  const evidenceBase = {
    candidate_count_before_filter: rawCandidates.length,
    candidate_count_after_filter: normalizedCandidates.length,
    canonical_candidate_count: effectiveExactMatchCount,
    rejected_candidate_count: Math.max(0, normalizedCandidates.length - effectiveExactMatchCount),
    conversation_candidates: rawCandidates,
    observed_conversation: normalizedObservedConversation || null,
  }

  if (effectiveExactMatchCount === 0) {
    return {
      ok: false,
      errorCode: 'TARGET_GROUP_NOT_FOUND',
      errorMessage: `未找到目标群聊“${conversationName}”，请确认企业微信中存在完全同名的群聊。`,
      stage: 'resolve_not_found',
      evidence: {
        step: 'resolve_not_found',
        ok: false,
        ...evidenceBase,
      },
    }
  }

  if (effectiveExactMatchCount > 1) {
    return {
      ok: false,
      errorCode: 'TARGET_GROUP_AMBIGUOUS',
      errorMessage: `存在多个名为“${conversationName}”的群聊，无法安全确定发送目标。`,
      stage: 'resolve_ambiguous',
      evidence: {
        step: 'resolve_ambiguous',
        ok: false,
        ...evidenceBase,
      },
    }
  }

  return {
    ok: true,
    evidence: {
      step: 'resolve_started',
      ok: true,
      ...evidenceBase,
    },
  }
}
