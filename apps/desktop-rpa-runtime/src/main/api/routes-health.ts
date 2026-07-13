import type { RuntimeStateStore } from '../runtime/state-store'

export function buildHealthPayload(stateStore: RuntimeStateStore) {
  return stateStore.getHealth()
}
