import type { RuntimeStateStore } from '../runtime/state-store'

export function buildRuntimeStatusPayload(stateStore: RuntimeStateStore) {
  return stateStore.getStatus()
}
