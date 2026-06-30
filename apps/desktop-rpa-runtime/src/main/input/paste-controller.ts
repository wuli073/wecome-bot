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
  let status: 'succeeded' | 'succeeded_with_warning' | 'blocked' | 'failed' | 'cancelled' | 'timed_out' = 'succeeded'
  let stage = 'queued'
  let errorCode: string | undefined
  let clipboardRestoreFailed = false
  let searchShortcutCount = 0
  let conversationPasteCount = 0
  let conversationConfirmEnterCount = 0
  let draftPasteCount = 0

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
    draftPasteCount += 1
    await deps.input.hotkey(['Control', 'V'])

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
    sendKeyCount: 0,
    idempotencyKey: request.idempotencyKey,
    requestDigest: request.requestDigest,
    ...extra,
  }
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
