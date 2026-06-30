import type { RuntimeTaskRequest } from '../domain/task-types'
import type { InputDriver } from './mouse-controller'

export async function runSendDraftTask(request: RuntimeTaskRequest, deps: { input: InputDriver; runtimeAutoSendEnabled: boolean; sendDriverForceDisabled?: boolean }): Promise<Record<string, unknown>> {
  if (deps.sendDriverForceDisabled || process.env.LANGBOT_RPA_FORCE_DISABLE_SEND === '1') {
    return { status: 'blocked', stage: 'send_driver_disabled', errorCode: 'SEND_DRIVER_DISABLED', sendAuthorized: false, messageSent: false }
  }
  if (!request.sendAuthorized || !request.allowAutoSend || !deps.runtimeAutoSendEnabled) {
    return { status: 'blocked', stage: 'auto_send_authorization', errorCode: 'AUTO_SEND_NOT_AUTHORIZED', sendAuthorized: false, messageSent: false }
  }
  if (!request.sendStrategy) {
    return { status: 'blocked', stage: 'send_strategy', errorCode: 'SEND_STRATEGY_REQUIRED', sendAuthorized: true, messageSent: false }
  }

  if (request.sendStrategy === 'enter') await deps.input.hotkey(['Enter'])
  else if (request.sendStrategy === 'ctrl_enter') await deps.input.hotkey(['Control', 'Enter'])
  else if (request.sendStrategy === 'click_send_button') await deps.input.click({ x: 0.9, y: 0.9 })
  else return { status: 'blocked', stage: 'send_strategy', errorCode: 'SEND_STRATEGY_UNSUPPORTED', sendAuthorized: true, messageSent: false }

  return { status: 'succeeded', stage: `sent_with_${request.sendStrategy}`, sendAuthorized: true, messageSent: true, strategy: request.sendStrategy }
}
