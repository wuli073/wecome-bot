import type { RuntimeTaskRequest } from '../domain/task-types'
import type { InputDriver } from './mouse-controller'

export async function runSendMessageTask(
  request: RuntimeTaskRequest,
  deps: { input: InputDriver; runtimeAutoSendEnabled: boolean; sendDriverForceDisabled?: boolean },
): Promise<Record<string, unknown>> {
  if (deps.sendDriverForceDisabled || process.env.LANGBOT_RPA_FORCE_DISABLE_SEND === '1') {
    return { status: 'blocked', stage: 'send_driver_disabled', errorCode: 'SEND_DRIVER_DISABLED', sendAuthorized: false, messageSent: false }
  }
  if (!deps.runtimeAutoSendEnabled) {
    return { status: 'blocked', stage: 'send_feature_flag', errorCode: 'SEND_FEATURE_DISABLED', sendAuthorized: false, messageSent: false }
  }
  if (!String(request.confirmationToken ?? '').trim()) {
    return { status: 'blocked', stage: 'confirmation_token', errorCode: 'CONFIRMATION_TOKEN_REQUIRED', sendAuthorized: false, messageSent: false }
  }

  await deps.input.hotkey(['Enter'])
  return {
    status: 'succeeded',
    stage: 'message_sent',
    sendAuthorized: true,
    messageSent: true,
    action: 'send_message',
  }
}
