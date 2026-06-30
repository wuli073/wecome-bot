export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'succeeded_with_warning' | 'blocked' | 'failed' | 'cancelled' | 'timed_out'
export type TaskAction = 'paste_draft' | 'send_draft' | 'diagnose' | 'conversation_search' | 'history_search' | 'quote_reply'
export type SendStrategy = 'enter' | 'ctrl_enter' | 'click_send_button'

export interface RuntimeTaskRequest {
  action: TaskAction
  idempotencyKey: string
  requestDigest: string
  conversationName?: string
  draftText?: string
  queryText?: string
  sendAuthorized?: boolean
  sendStrategy?: SendStrategy
  allowAutoSend?: boolean
}

export interface RuntimeTask {
  id: string
  action: TaskAction
  idempotencyKey: string
  requestDigest: string
  windowKey: string
  status: TaskStatus
  stage: string
  createdAt: string
  updatedAt: string
  sendAuthorized?: boolean
  messageSent?: boolean
  clipboardRestoreFailed?: boolean
  errorCode?: string
  result?: Record<string, unknown>
}
