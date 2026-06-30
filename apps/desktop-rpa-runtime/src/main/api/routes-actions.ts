import type { RuntimeTaskRequest } from '../domain/task-types'
import type { RuntimeHost } from '../runtime/runtime-host'

export async function createRuntimeTask(host: RuntimeHost, request: RuntimeTaskRequest) {
  return host.createTask(request)
}
