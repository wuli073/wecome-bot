/**
 * Data source factory
 * Creates the appropriate data source based on bot adapter type
 */

import type { BotSessionDataSource } from '../types';
import { DatabaseBotDataSource } from './DatabaseBotDataSource';
import { RuntimeBotDataSource } from './RuntimeBotDataSource';

/**
 * Create a data source based on the bot adapter
 * @param botAdapter - The adapter type (e.g., 'wxwork_database', 'wxwork', etc.)
 * @param botId - The bot UUID
 * @returns Appropriate data source implementation
 */
export function createDataSource(
  botAdapter: string,
  botId: string,
): BotSessionDataSource {
  if (botAdapter === 'wxwork_database') {
    return new DatabaseBotDataSource(botId);
  }
  return new RuntimeBotDataSource(botId);
}

/**
 * Determine if a bot uses database mode based on its adapter
 */
export function isDatabaseModeBot(botAdapter: string): boolean {
  return botAdapter === 'wxwork_database';
}
