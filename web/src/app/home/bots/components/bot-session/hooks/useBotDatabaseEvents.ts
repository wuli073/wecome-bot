/**
 * Bot Database Events Hook
 * Wrapper around useDatabaseModeEvents for use in Bot Session Monitor
 */

import { useDatabaseModeEvents } from '@/app/home/database-mode/hooks/useDatabaseModeEvents';
import type { DatabaseModeRealtimeEvent } from '@/app/infra/entities/api';

interface UseBotDatabaseEventsProps {
  enabled: boolean;
  onMessageCreated?: (event: DatabaseModeRealtimeEvent) => void;
  onMessageUpdated?: (event: DatabaseModeRealtimeEvent) => void;
  onConversationUpdated?: (event: DatabaseModeRealtimeEvent) => void;
  onMessageDeleted?: (event: DatabaseModeRealtimeEvent) => void;
}

/**
 * Hook to subscribe to database mode events for a specific bot
 * Reuses the existing useDatabaseModeEvents connection
 */
export function useBotDatabaseEvents({
  enabled,
  onMessageCreated,
  onMessageUpdated,
  onConversationUpdated,
  onMessageDeleted,
}: UseBotDatabaseEventsProps) {
  const handleEvent = (event: DatabaseModeRealtimeEvent) => {
    // Filter events by bot if needed (for now, all database mode events are global)
    switch (event.type) {
      case 'database-message-created':
        onMessageCreated?.(event);
        break;
      case 'database-message-updated':
        onMessageUpdated?.(event);
        break;
      case 'database-conversation-updated':
        onConversationUpdated?.(event);
        break;
      case 'database-message-deleted':
        onMessageDeleted?.(event);
        break;
      default:
        break;
    }
  };

  const { connectionState } = useDatabaseModeEvents({
    enabled,
    onEvent: handleEvent,
  });

  return { connectionState };
}
