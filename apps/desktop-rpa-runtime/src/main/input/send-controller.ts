import type { RuntimeTaskRequest } from '../domain/task-types'
import type { WindowDescriptor } from '../domain/window-types'
import type { PasteTaskDeps, PrepareDraftInputResult } from './paste-controller'
import { PASTE_SETTLE_DELAY_MS, prepareDraftInput } from './paste-controller'
import type { InputDriver } from './mouse-controller'

interface PostSendVerifyResult {
  verified: boolean
  verification_method: string
  verification_result: string
  error_code?: string
  error_message?: string
  evidence?: Array<Record<string, unknown>>
}

export interface SendTaskDeps extends Partial<PasteTaskDeps> {
  input: InputDriver
  runtimeAutoSendEnabled: boolean
  sendDriverForceDisabled?: boolean
  prepareDraftInput?: (request: RuntimeTaskRequest, deps: PasteTaskDeps) => Promise<PrepareDraftInputResult>
  postSendVerify?: (
    request: RuntimeTaskRequest,
    prepared: PrepareDraftInputResult,
    deps: SendTaskDeps,
  ) => Promise<PostSendVerifyResult>
}

export async function runSendMessageTask(
  request: RuntimeTaskRequest,
  deps: SendTaskDeps,
): Promise<Record<string, unknown>> {
  if (deps.sendDriverForceDisabled || process.env.LANGBOT_RPA_FORCE_DISABLE_SEND === '1') {
    return { status: 'blocked', stage: 'send_driver_disabled', errorCode: 'SEND_DRIVER_DISABLED', sendAuthorized: false, messageSent: false }
  }
  if (!deps.runtimeAutoSendEnabled) {
    return { status: 'blocked', stage: 'send_feature_flag', errorCode: 'SEND_FEATURE_DISABLED', sendAuthorized: false, messageSent: false }
  }

  const prepare = deps.prepareDraftInput ?? prepareDraftInput
  const rawPrepared = await prepare(request, deps as PasteTaskDeps)
  const rawPreparedRecord = rawPrepared as unknown as Record<string, unknown>
  const prepared: PrepareDraftInputResult = 'runtimeResult' in rawPreparedRecord
    ? rawPrepared as PrepareDraftInputResult
    : {
        activeWindow: (rawPreparedRecord.activeWindow ?? null) as WindowDescriptor | null,
        runtimeResult: rawPreparedRecord,
      }
  const prepareResult = prepared.runtimeResult
  if (
    !('runtimeResult' in rawPreparedRecord)
    && ['succeeded', 'succeeded_with_warning'].includes(String(prepareResult.status || ''))
  ) {
    prepareResult.status = 'prepared'
  }
  if (String(prepareResult.status) !== 'prepared') {
    const errorCode = String(prepareResult.errorCode ?? prepareResult.error_code ?? 'PREPARE_DRAFT_INPUT_FAILED')
    const errorMessage = String(prepareResult.errorMessage ?? prepareResult.error_message ?? errorCode)
    return buildSendResult({
      request,
      status: String(prepareResult.status || 'failed') === 'blocked' ? 'failed' : String(prepareResult.status || 'failed'),
      stage: String(prepareResult.stage || 'prepare_failed'),
      outcome: 'failed',
      enterDispatched: false,
      postSendVerified: false,
      verificationMethod: String(prepareResult.verificationMethod ?? 'not_run'),
      verificationResult: 'not_run',
      errorCode,
      errorMessage,
      evidence: normalizeEvidence(prepareResult.evidence),
      messageSent: false,
      terminalConfirmed: true,
      retryAllowed: false,
    })
  }

  const sleep = deps.sleep ?? defaultSleep
  try {
    await sleep(PASTE_SETTLE_DELAY_MS)
    await deps.input.hotkey(['Enter'])
  } catch (error) {
    const errorCode = error instanceof Error && error.message ? error.message : 'ENTER_DISPATCH_FAILED'
    return buildSendResult({
      request,
      status: 'failed',
      stage: 'enter_dispatch_failed',
      outcome: 'failed',
      enterDispatched: false,
      postSendVerified: false,
      verificationMethod: 'enter',
      verificationResult: 'enter_failed',
      errorCode,
      errorMessage: errorCode,
      evidence: [...normalizeEvidence(prepareResult.evidence), { step: 'enter', ok: false, error_code: errorCode }],
      messageSent: false,
      terminalConfirmed: true,
      retryAllowed: false,
    })
  }

  const verify = deps.postSendVerify ?? defaultPostSendVerify
  const verification = await verify(request, prepared, deps)
  const baseEvidence = [
    ...normalizeEvidence(prepareResult.evidence),
    { step: 'enter', ok: true, key: 'Enter' },
    ...normalizeEvidence(verification.evidence),
  ]

  if (verification.verified) {
    return buildSendResult({
      request,
      status: 'succeeded',
      stage: 'sent',
      outcome: 'sent',
      enterDispatched: true,
      postSendVerified: true,
      verificationMethod: verification.verification_method,
      verificationResult: verification.verification_result,
      evidence: baseEvidence,
      messageSent: true,
      terminalConfirmed: true,
      retryAllowed: false,
    })
  }

  return buildSendResult({
    request,
    status: 'succeeded_with_warning',
    stage: 'sent_unconfirmed',
    outcome: 'unknown',
    enterDispatched: true,
    postSendVerified: false,
    verificationMethod: verification.verification_method,
    verificationResult: verification.verification_result,
    errorCode: verification.error_code ?? 'POST_SEND_VERIFICATION_FAILED',
    errorMessage: verification.error_message ?? verification.error_code ?? 'POST_SEND_VERIFICATION_FAILED',
    evidence: baseEvidence,
    messageSent: null,
    terminalConfirmed: false,
    retryAllowed: false,
  })
}

async function defaultPostSendVerify(
  _request: RuntimeTaskRequest,
  _prepared: PrepareDraftInputResult,
  _deps: SendTaskDeps,
): Promise<PostSendVerifyResult> {
  return {
    verified: false,
    verification_method: 'not_available',
    verification_result: 'not_confirmed',
    error_code: 'POST_SEND_VERIFICATION_UNAVAILABLE',
    error_message: 'Post-send confirmation is not available in the fixed keyboard flow',
    evidence: [{
      step: 'post_send_verify',
      ok: false,
      reason: 'confirmation_skipped',
    }],
  }
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function normalizeEvidence(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    : []
}

function buildSendResult(args: {
  request: RuntimeTaskRequest
  status: string
  stage: string
  outcome: 'sent' | 'unknown' | 'failed'
  enterDispatched: boolean
  postSendVerified: boolean
  verificationMethod: string
  verificationResult: string
  errorCode?: string
  errorMessage?: string
  evidence: Array<Record<string, unknown>>
  messageSent: boolean | null
  terminalConfirmed: boolean
  retryAllowed: boolean
}) {
  const sendKeyCount = args.enterDispatched ? 1 : 0
  return {
    status: args.status,
    stage: args.stage,
    action: args.request.action,
    sendAuthorized: true,
    messageSent: args.messageSent,
    message_sent: args.messageSent,
    sendTriggered: args.enterDispatched,
    sendKeyCount,
    send_key_count: sendKeyCount,
    outcome: args.outcome,
    enterDispatched: args.enterDispatched,
    enter_dispatched: args.enterDispatched,
    terminalConfirmed: args.terminalConfirmed,
    terminal_confirmed: args.terminalConfirmed,
    retryAllowed: args.retryAllowed,
    retry_allowed: args.retryAllowed,
    postSendVerified: args.postSendVerified,
    post_send_verified: args.postSendVerified,
    verificationMethod: args.verificationMethod,
    verification_method: args.verificationMethod,
    verificationResult: args.verificationResult,
    verification_result: args.verificationResult,
    ...(args.errorCode ? { errorCode: args.errorCode, error_code: args.errorCode } : {}),
    ...(args.errorMessage ? { errorMessage: args.errorMessage, error_message: args.errorMessage } : {}),
    evidence: args.evidence,
  }
}
