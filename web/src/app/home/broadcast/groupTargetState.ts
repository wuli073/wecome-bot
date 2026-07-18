import type { BroadcastGroupName } from './types';

export type GroupTargetState = {
  selectable: boolean;
  resolutionMode: 'stable_id' | 'name' | 'invalid';
  labelKey: 'stableIdReady' | 'nameMatch' | 'invalid';
};

/** Derive the one target-group state shared by every broadcast entry point. */
export function getGroupTargetState(
  group: Pick<BroadcastGroupName, 'externalConversationId' | 'name'>,
): GroupTargetState {
  if (group.externalConversationId?.trim()) {
    return { selectable: true, resolutionMode: 'stable_id', labelKey: 'stableIdReady' };
  }
  if (group.name.trim()) {
    return { selectable: true, resolutionMode: 'name', labelKey: 'nameMatch' };
  }
  return { selectable: false, resolutionMode: 'invalid', labelKey: 'invalid' };
}
