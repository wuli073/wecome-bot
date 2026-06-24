import { useEffect, useEffectEvent, useState } from 'react';

import type {
  DatabaseModeRealtimeEvent,
  DatabaseModeRealtimeEventType,
} from '@/app/infra/entities/api';
import { backendClient, httpClient } from '@/app/infra/http';

function buildEventSourceUrl(): string {
  const baseUrl = backendClient.getBaseUrl();
  if (!baseUrl || baseUrl === '/') {
    return '/api/v1/database-mode/events';
  }

  const trimmedBaseUrl = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
  return `${trimmedBaseUrl}/api/v1/database-mode/events`;
}

const EVENT_TYPES: DatabaseModeRealtimeEventType[] = [
  'ready',
  'database-message-created',
  'database-message-updated',
  'database-message-deleted',
  'database-conversation-updated',
  'database-mode-invalidated',
];
const CONNECTION_CLEANUP_DELAY_MS = 1_000;
const EVENT_SESSION_TIMEOUT_MS = 1_000;
const EVENT_SOURCE_OPEN_TIMEOUT_MS = 1_000;

type DatabaseModeEventLifecycleStage =
  | 'handshake_started'
  | 'handshake_completed'
  | 'event_source_created'
  | 'event_source_opened'
  | 'ready_received'
  | 'retry_scheduled'
  | 'close_requested';

type DatabaseModeCloseReason =
  | 'application_cleanup'
  | 'disabled'
  | 'event_source_error'
  | 'event_source_init_failed'
  | 'handshake_failed'
  | 'last_listener_removed'
  | 'no_listeners_after_handshake'
  | 'open_timeout';

type DatabaseModeConnectionAttempt = {
  generation: number;
  sourceId: string;
  startedAt: number;
};

export type DatabaseModeEventLifecycleLog = {
  stage: DatabaseModeEventLifecycleStage;
  generation: number;
  source_id: string;
  elapsed_ms: number;
  close_reason: DatabaseModeCloseReason | null;
};

declare global {
  interface Window {
    __databaseModeEventLifecycleLogs?: DatabaseModeEventLifecycleLog[];
  }
}

type DatabaseModeListener = {
  onEvent: (event: DatabaseModeRealtimeEvent) => void;
  onStateChange: (state: DatabaseModeEventConnectionState) => void;
};

export type DatabaseModeEventConnectionState =
  | 'idle'
  | 'handshaking'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'retrying';

let sharedSource: EventSource | null = null;
let sharedRetryTimer: number | null = null;
let sharedDisposeTimer: number | null = null;
let sharedOpenTimeoutTimer: number | null = null;
let sharedRetryCount = 0;
let sharedConnecting = false;
let sharedConnectionGeneration = 0;
let sharedConnectionAttemptCounter = 0;
let sharedListenerEpoch = 0;
let sharedState: DatabaseModeEventConnectionState = 'idle';
let sharedAttempt: DatabaseModeConnectionAttempt | null = null;
const sharedListeners = new Set<DatabaseModeListener>();

function recordLifecycleLog(
  stage: DatabaseModeEventLifecycleStage,
  attempt: DatabaseModeConnectionAttempt,
  closeReason: DatabaseModeCloseReason | null = null,
) {
  const entry: DatabaseModeEventLifecycleLog = {
    stage,
    generation: attempt.generation,
    source_id: attempt.sourceId,
    elapsed_ms: Math.max(0, Date.now() - attempt.startedAt),
    close_reason: closeReason,
  };

  if (typeof window !== 'undefined') {
    const existingLogs = window.__databaseModeEventLifecycleLogs ?? [];
    existingLogs.push(entry);
    window.__databaseModeEventLifecycleLogs = existingLogs;
  }

  console.info('[database-mode-events]', entry);
}

function beginConnectionAttempt(): DatabaseModeConnectionAttempt {
  const attempt: DatabaseModeConnectionAttempt = {
    generation: sharedConnectionGeneration + 1,
    sourceId: `dbmode-sse-${++sharedConnectionAttemptCounter}`,
    startedAt: Date.now(),
  };
  sharedConnectionGeneration = attempt.generation;
  sharedAttempt = attempt;
  recordLifecycleLog('handshake_started', attempt);
  return attempt;
}

function emitState(state: DatabaseModeEventConnectionState) {
  sharedState = state;
  for (const listener of sharedListeners) {
    listener.onStateChange(state);
  }
}

function clearDisposeTimer() {
  if (sharedDisposeTimer == null) {
    return;
  }
  window.clearTimeout(sharedDisposeTimer);
  sharedDisposeTimer = null;
}

function clearRetryTimer() {
  if (sharedRetryTimer == null) {
    return;
  }
  window.clearTimeout(sharedRetryTimer);
  sharedRetryTimer = null;
}

function clearOpenTimeoutTimer() {
  if (sharedOpenTimeoutTimer == null) {
    return;
  }
  window.clearTimeout(sharedOpenTimeoutTimer);
  sharedOpenTimeoutTimer = null;
}

function markConnectionConnected(source: EventSource, attempt: DatabaseModeConnectionAttempt) {
  if (sharedSource !== source || attempt.generation !== sharedConnectionGeneration) {
    return;
  }
  clearOpenTimeoutTimer();
  sharedRetryCount = 0;
  sharedConnecting = false;
  emitState('connected');
}

function cleanupSharedSource(
  closeReason: DatabaseModeCloseReason,
  attempt: DatabaseModeConnectionAttempt | null = sharedAttempt,
) {
  clearDisposeTimer();
  clearRetryTimer();
  clearOpenTimeoutTimer();

  if (sharedSource != null) {
    if (attempt != null) {
      recordLifecycleLog('close_requested', attempt, closeReason);
    }
    sharedSource.onopen = null;
    sharedSource.onerror = null;
    sharedSource.close();
  }
  sharedSource = null;
  sharedConnecting = false;
}

function emitEvent(event: DatabaseModeRealtimeEvent) {
  for (const listener of sharedListeners) {
    listener.onEvent(event);
  }
}

function scheduleReconnect(
  closeReason: DatabaseModeCloseReason,
  attempt: DatabaseModeConnectionAttempt | null = sharedAttempt,
) {
  const retryGeneration = attempt?.generation ?? sharedConnectionGeneration;
  cleanupSharedSource(closeReason, attempt);
  emitState('disconnected');
  if (sharedListeners.size === 0) {
    emitState('idle');
    return;
  }

  emitState('retrying');
  const delay = Math.min(30_000, 1_000 * 2 ** sharedRetryCount);
  if (attempt != null) {
    recordLifecycleLog('retry_scheduled', attempt, closeReason);
  }
  sharedRetryTimer = window.setTimeout(() => {
    sharedRetryTimer = null;
    if (sharedSource !== null || retryGeneration !== sharedConnectionGeneration) {
      return;
    }
    sharedRetryCount += 1;
    void ensureConnection();
  }, delay);
}

async function ensureConnection() {
  clearDisposeTimer();
  clearRetryTimer();

  if (sharedConnecting || sharedSource != null || sharedListeners.size === 0) {
    return;
  }

  sharedConnecting = true;
  emitState('handshaking');
  const attempt = beginConnectionAttempt();

  try {
    await httpClient.createDatabaseModeEventSession({
      timeout: EVENT_SESSION_TIMEOUT_MS,
    });
  } catch (_error) {
    if (sharedConnectionGeneration !== attempt.generation) {
      return;
    }
    sharedConnecting = false;
    scheduleReconnect('handshake_failed', attempt);
    return;
  }

  if (sharedConnectionGeneration !== attempt.generation) {
    return;
  }
  recordLifecycleLog('handshake_completed', attempt);

  if (sharedListeners.size === 0) {
    cleanupSharedSource('no_listeners_after_handshake', attempt);
    emitState('idle');
    return;
  }

  let source: EventSource;
  try {
    source = new EventSource(buildEventSourceUrl(), {
      withCredentials: true,
    });
  } catch (_error) {
    sharedConnecting = false;
    scheduleReconnect('event_source_init_failed', attempt);
    return;
  }
  sharedSource = source;
  let readyHandled = false;
  let openHandled = false;
  emitState('connecting');
  recordLifecycleLog('event_source_created', attempt);

  clearOpenTimeoutTimer();
  sharedOpenTimeoutTimer = window.setTimeout(() => {
    if (sharedSource !== source || attempt.generation !== sharedConnectionGeneration) {
      return;
    }
    sharedConnecting = false;
    scheduleReconnect('open_timeout', attempt);
  }, EVENT_SOURCE_OPEN_TIMEOUT_MS);

  const markEventSourceOpened = () => {
    if (openHandled) {
      return;
    }
    openHandled = true;
    recordLifecycleLog('event_source_opened', attempt);
  };

  source.onopen = () => {
    markEventSourceOpened();
    markConnectionConnected(source, attempt);
  };

  source.onerror = () => {
    if (sharedSource !== source || attempt.generation !== sharedConnectionGeneration) {
      return;
    }
    clearOpenTimeoutTimer();
    sharedConnecting = false;
    scheduleReconnect('event_source_error', attempt);
  };

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (event) => {
      if (sharedSource !== source || attempt.generation !== sharedConnectionGeneration) {
        return;
      }
      try {
        const payload = JSON.parse((event as MessageEvent).data) as DatabaseModeRealtimeEvent;
        if (payload.type === 'ready') {
          if (readyHandled) {
            return;
          }

          readyHandled = true;
          recordLifecycleLog('ready_received', attempt);
          markConnectionConnected(source, attempt);
        }
        emitEvent(payload);
      } catch (_error) {
        // Ignore malformed events and wait for the next reconnect/refresh.
      }
    });
  }

  if (source.readyState === EventSource.OPEN) {
    markEventSourceOpened();
    markConnectionConnected(source, attempt);
  }
}

export function useDatabaseModeEvents({
  enabled,
  onEvent,
}: {
  enabled: boolean;
  onEvent: (event: DatabaseModeRealtimeEvent) => void;
}) {
  const [connectionState, setConnectionState] =
    useState<DatabaseModeEventConnectionState>(sharedState);

  const eventHandler = useEffectEvent(onEvent);
  const stateChangeHandler = useEffectEvent(
    (state: DatabaseModeEventConnectionState) => {
      setConnectionState(state);
    },
  );

  useEffect(() => {
    if (!enabled) {
      if (sharedSource != null && sharedListeners.size === 0) {
        cleanupSharedSource('disabled');
      }
      setConnectionState(sharedListeners.size === 0 ? 'idle' : 'disconnected');
      return;
    }

    sharedListenerEpoch += 1;
    clearDisposeTimer();

    const listener: DatabaseModeListener = {
      onEvent: (event) => eventHandler(event),
      onStateChange: (state) => stateChangeHandler(state),
    };

    sharedListeners.add(listener);
    listener.onStateChange(sharedState);
    void ensureConnection();

    return () => {
      sharedListeners.delete(listener);
      sharedListenerEpoch += 1;
      if (sharedListeners.size === 0) {
        const cleanupEpoch = sharedListenerEpoch;
        const cleanupGeneration = sharedConnectionGeneration;
        const cleanupSource = sharedSource;
        sharedDisposeTimer = window.setTimeout(() => {
          sharedDisposeTimer = null;
          if (sharedListeners.size !== 0) {
            return;
          }
          if (sharedListenerEpoch !== cleanupEpoch) {
            return;
          }
          if (sharedConnectionGeneration !== cleanupGeneration) {
            return;
          }
          if (sharedSource !== cleanupSource) {
            return;
          }
          cleanupSharedSource('last_listener_removed');
          emitState('idle');
        }, CONNECTION_CLEANUP_DELAY_MS);
      }
    };
  }, [enabled]);

  return { connectionState };
}
