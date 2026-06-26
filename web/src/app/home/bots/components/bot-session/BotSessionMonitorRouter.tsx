/**
 * Bot Session Monitor Router
 * Routes to appropriate monitor based on bot adapter type
 */

import React, { forwardRef, useImperativeHandle } from 'react';
import { isDatabaseModeBot } from './datasources';
import BotSessionMonitorRuntime from './BotSessionMonitor';
import { DatabaseBotSessionMonitor } from './components/DatabaseBotSessionMonitor';
import type { BotSessionMonitorHandle } from './BotSessionMonitor';

interface BotSessionMonitorRouterProps {
  botId: string;
  botAdapter: string;
  botEnabled: boolean;
}

const BotSessionMonitorRouter = forwardRef<
  BotSessionMonitorHandle,
  BotSessionMonitorRouterProps
>(function BotSessionMonitorRouter({ botId, botAdapter, botEnabled }, ref) {
  const runtimeRef = React.useRef<BotSessionMonitorHandle>(null);
  const databaseRef = React.useRef<BotSessionMonitorHandle>(null);

  useImperativeHandle(
    ref,
    () => ({
      refreshSessions: async () => {
        if (isDatabaseModeBot(botAdapter)) {
          await databaseRef.current?.refreshSessions();
        } else {
          await runtimeRef.current?.refreshSessions();
        }
      },
    }),
    [botAdapter],
  );

  if (isDatabaseModeBot(botAdapter)) {
    return (
      <DatabaseBotSessionMonitor
        ref={databaseRef}
        botId={botId}
        botAdapter={botAdapter}
        botEnabled={botEnabled}
      />
    );
  }

  return <BotSessionMonitorRuntime ref={runtimeRef} botId={botId} />;
});

export default BotSessionMonitorRouter;
