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

type DatabaseModeListener = {
  onConnectRefresh: () => void;
  onEvent: (event: DatabaseModeRealtimeEvent) => void;
  onStateChange: (state: DatabaseModeEventConnectionState) => void;
};

export type DatabaseModeEventConnectionState =
  | 'connecting'
  | 'connected'
  | 'disconnected';

let sharedSource: EventSource | null = null;
let sharedRetryTimer: number | null = null;
let sharedDisposeTimer: number | null = null;
let sharedRetryCount = 0;
let sharedConnecting = false;
let sharedState: DatabaseModeEventConnectionState = 'disconnected';
const sharedListeners = new Set<DatabaseModeListener>();

function emitState(state: DatabaseModeEventConnectionState) {
  sharedState = state;
  for (const listener of sharedListeners) {
    listener.onStateChange(state);
  }
}

function cleanupSharedSource() {
  if (sharedDisposeTimer != null) {
    window.clearTimeout(sharedDisposeTimer);
  }
  sharedDisposeTimer = null;
  if (sharedRetryTimer != null) {
    window.clearTimeout(sharedRetryTimer);
  }
  sharedRetryTimer = null;

  if (sharedSource != null) {
    sharedSource.close();
  }
  sharedSource = null;
  sharedConnecting = false;
}

function emitEvent(event: DatabaseModeRealtimeEvent) {
  for (const listener of sharedListeners) {
    if (event.type === 'ready') {
      listener.onConnectRefresh();
    }
    listener.onEvent(event);
  }
}

function emitConnectRefresh() {
  for (const listener of sharedListeners) {
    listener.onConnectRefresh();
  }
}

function scheduleReconnect() {
  cleanupSharedSource();
  emitState('disconnected');
  if (sharedListeners.size === 0) {
    return;
  }

  const delay = Math.min(30_000, 1_000 * 2 ** sharedRetryCount);
  sharedRetryTimer = window.setTimeout(() => {
    sharedRetryCount += 1;
    void ensureConnection();
  }, delay);
}

async function ensureConnection() {
  if (sharedDisposeTimer != null) {
    window.clearTimeout(sharedDisposeTimer);
  }
  sharedDisposeTimer = null;

  if (sharedConnecting || sharedSource != null || sharedListeners.size === 0) {
    return;
  }

  sharedConnecting = true;
  emitState('connecting');

  try {
    await httpClient.createDatabaseModeEventSession();
  } catch (_error) {
    sharedConnecting = false;
    scheduleReconnect();
    return;
  }

  const source = new EventSource(buildEventSourceUrl(), {
    withCredentials: true,
  });
  sharedSource = source;

  source.onopen = () => {
    sharedRetryCount = 0;
    sharedConnecting = false;
    emitState('connected');
    emitConnectRefresh();
  };

  source.onerror = () => {
    sharedConnecting = false;
    scheduleReconnect();
  };

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as DatabaseModeRealtimeEvent;
        emitEvent(payload);
      } catch (_error) {
        // Ignore malformed events and wait for the next reconnect/refresh.
      }
    });
  }
}

export function useDatabaseModeEvents({
  enabled,
  onConnectRefresh,
  onEvent,
}: {
  enabled: boolean;
  onConnectRefresh: () => void;
  onEvent: (event: DatabaseModeRealtimeEvent) => void;
}) {
  const [connectionState, setConnectionState] =
    useState<DatabaseModeEventConnectionState>(sharedState);

  const connectRefreshHandler = useEffectEvent(onConnectRefresh);
  const eventHandler = useEffectEvent(onEvent);
  const stateChangeHandler = useEffectEvent(
    (state: DatabaseModeEventConnectionState) => {
      setConnectionState(state);
    },
  );

  useEffect(() => {
    if (!enabled) {
      setConnectionState('disconnected');
      return;
    }

    const listener: DatabaseModeListener = {
      onConnectRefresh: () => connectRefreshHandler(),
      onEvent: (event) => eventHandler(event),
      onStateChange: (state) => stateChangeHandler(state),
    };

    sharedListeners.add(listener);
    listener.onStateChange(sharedState);
    void ensureConnection();

    return () => {
      sharedListeners.delete(listener);
      if (sharedListeners.size === 0) {
        sharedDisposeTimer = window.setTimeout(() => {
          if (sharedListeners.size === 0) {
            cleanupSharedSource();
            emitState('disconnected');
          }
        }, 0);
      }
    };
  }, [enabled]);

  return { connectionState };
}
