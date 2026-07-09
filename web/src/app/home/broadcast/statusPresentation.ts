import type {
  BroadcastExecutionBatchSummary,
  BroadcastExecutionLog,
  BroadcastExecutionTaskSummary,
} from './types';

const BATCH_STATUS_KEYS: Record<string, string> = {
  created: 'broadcast.logs.batchStatuses.created',
  queued: 'broadcast.logs.batchStatuses.queued',
  running: 'broadcast.logs.batchStatuses.running',
  paused: 'broadcast.logs.batchStatuses.paused',
  completed: 'broadcast.logs.batchStatuses.completed',
  partially_failed: 'broadcast.logs.batchStatuses.partially_failed',
  failed: 'broadcast.logs.batchStatuses.failed',
  cancelled: 'broadcast.logs.batchStatuses.cancelled',
  interrupted: 'broadcast.logs.batchStatuses.interrupted',
};

const TASK_STATUS_KEYS: Record<string, string> = {
  pending: 'broadcast.logs.taskStatuses.pending',
  queued: 'broadcast.logs.taskStatuses.queued',
  running: 'broadcast.logs.taskStatuses.running',
  succeeded: 'broadcast.logs.taskStatuses.succeeded',
  succeeded_with_warning: 'broadcast.logs.taskStatuses.succeeded_with_warning',
  blocked: 'broadcast.logs.taskStatuses.blocked',
  failed: 'broadcast.logs.taskStatuses.failed',
  cancelled: 'broadcast.logs.taskStatuses.cancelled',
  timed_out: 'broadcast.logs.taskStatuses.timed_out',
  interrupted: 'broadcast.logs.taskStatuses.interrupted',
};

const EXECUTION_ADVICE_KEYS: Record<string, string> = {
  TARGET_WINDOW_NOT_FOUND:
    'broadcast.logs.errorSuggestions.TARGET_WINDOW_NOT_FOUND',
  TARGET_WINDOW_AMBIGUOUS:
    'broadcast.logs.errorSuggestions.TARGET_WINDOW_AMBIGUOUS',
  WINDOW_ACTIVATION_FAILED:
    'broadcast.logs.errorSuggestions.WINDOW_ACTIVATION_FAILED',
  SEARCH_ACTIVATION_FAILED:
    'broadcast.logs.errorSuggestions.SEARCH_ACTIVATION_FAILED',
  TARGET_WINDOW_LOST_BEFORE_ATTACHMENT_PASTE:
    'broadcast.logs.errorSuggestions.TARGET_WINDOW_LOST_BEFORE_ATTACHMENT_PASTE',
  CONVERSATION_NAME_PASTE_FAILED:
    'broadcast.logs.errorSuggestions.CONVERSATION_NAME_PASTE_FAILED',
  SEARCH_RESULT_CONFIRM_FAILED:
    'broadcast.logs.errorSuggestions.SEARCH_RESULT_CONFIRM_FAILED',
  ATTACHMENT_FILE_MISSING:
    'broadcast.logs.errorSuggestions.ATTACHMENT_FILE_MISSING',
  ATTACHMENT_HASH_MISMATCH:
    'broadcast.logs.errorSuggestions.ATTACHMENT_HASH_MISMATCH',
  ATTACHMENT_PATH_OUTSIDE_ROOT:
    'broadcast.logs.errorSuggestions.ATTACHMENT_PATH_OUTSIDE_ROOT',
  FILE_CLIPBOARD_HELPER_FAILED:
    'broadcast.logs.errorSuggestions.FILE_CLIPBOARD_HELPER_FAILED',
  FILE_CLIPBOARD_HELPER_TIMEOUT:
    'broadcast.logs.errorSuggestions.FILE_CLIPBOARD_HELPER_TIMEOUT',
  CLIPBOARD_RESTORE_MISMATCH:
    'broadcast.logs.errorSuggestions.CLIPBOARD_RESTORE_MISMATCH',
  PASTE_RESULT_NOT_VERIFIED:
    'broadcast.logs.errorSuggestions.PASTE_RESULT_NOT_VERIFIED',
};

export function getExecutionBatchStatusKey(status: string) {
  return (
    BATCH_STATUS_KEYS[String(status || '').trim()] ??
    'broadcast.logs.batchStatuses.unknown'
  );
}

export function getExecutionTaskStatusKey(status: string) {
  return (
    TASK_STATUS_KEYS[String(status || '').trim()] ??
    'broadcast.logs.taskStatuses.unknown'
  );
}

export function isRetryableExecutionTask(task: BroadcastExecutionTaskSummary) {
  if (typeof task.retryAllowed === 'boolean') {
    return task.retryAllowed;
  }
  return false;
}

export function isRetryableExecutionTaskStatus(status: string) {
  return status === 'failed' || status === 'interrupted';
}

export function getRetryableExecutionTasks(
  batch: BroadcastExecutionBatchSummary | null | undefined,
) {
  return (batch?.tasks ?? []).filter(isRetryableExecutionTask);
}

export function getExecutionAdviceKey(code?: string | null) {
  if (!code) {
    return null;
  }
  return (
    EXECUTION_ADVICE_KEYS[code] ?? 'broadcast.logs.errorSuggestions.__default'
  );
}

export function getExecutionTaskAdviceKey(task: BroadcastExecutionTaskSummary) {
  if (task.status === 'succeeded_with_warning') {
    return getExecutionAdviceKey('PASTE_RESULT_NOT_VERIFIED');
  }
  return getExecutionAdviceKey(task.errorCode);
}

export function getExecutionLogAdviceCode(log: BroadcastExecutionLog) {
  return log.warning || log.errorCode || null;
}

export function getExecutionLogStatusKey(log: BroadcastExecutionLog) {
  if (log.taskStatus === 'succeeded_with_warning') {
    return 'broadcast.logs.statusWarning';
  }
  if (log.action === 'send_message' && log.sendTriggered) {
    return 'broadcast.logs.statusSendTriggered';
  }
  if (log.contentVerified) {
    return 'broadcast.logs.statusPasteVerified';
  }
  if (log.draftWritten && !log.sendTriggered) {
    return 'broadcast.logs.statusDraftWritten';
  }
  return getExecutionTaskStatusKey(log.taskStatus);
}

export function getExecutionBatchActionVisibility(
  batch: BroadcastExecutionBatchSummary | null | undefined,
) {
  if (!batch) {
    return {
      start: false,
      pause: false,
      resume: false,
      cancel: false,
      retryFailed: false,
    };
  }

  const retryableTaskCount = getRetryableExecutionTasks(batch).length;

  return {
    start: batch.status === 'created',
    pause: batch.status === 'queued' || batch.status === 'running',
    resume: batch.status === 'paused' || batch.status === 'interrupted',
    cancel:
      batch.status === 'created' ||
      batch.status === 'queued' ||
      batch.status === 'running' ||
      batch.status === 'paused',
    retryFailed:
      ['partially_failed', 'failed', 'interrupted'].includes(batch.status) &&
      retryableTaskCount > 0,
  };
}
