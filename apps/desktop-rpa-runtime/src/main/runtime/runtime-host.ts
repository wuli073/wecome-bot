import type { RuntimeTaskRequest } from '../domain/task-types'
import { PerWindowTaskLock } from './task-locks'
import { TaskRegistry } from './task-registry'
import { TaskRunner, type TaskRunnerOptions } from './task-runner'

export class RuntimeHost {
  readonly registry = new TaskRegistry()
  readonly locks = new PerWindowTaskLock()
  readonly runner: TaskRunner

  constructor(options: TaskRunnerOptions = {}) {
    this.runner = new TaskRunner(options)
  }

  async createTask(request: RuntimeTaskRequest) {
    const { task, reused } = this.registry.createOrGet(request)
    if (reused) return task
    if (!this.locks.acquire(task.windowKey)) {
      return this.registry.update(task, { status: 'queued', stage: 'queued_for_window_lock' })
    }
    try {
      this.registry.update(task, { status: 'running', stage: 'running' })
      const result = await this.runner.run(request)
      return this.registry.update(task, {
        status: (result.status as never) ?? 'failed',
        stage: String(result.stage ?? 'completed'),
        sendAuthorized: Boolean(result.sendAuthorized),
        messageSent: Boolean(result.messageSent),
        clipboardRestoreFailed: Boolean(result.clipboardRestoreFailed),
        errorCode: typeof result.errorCode === 'string' ? result.errorCode : undefined,
        result,
      })
    } finally {
      this.locks.release(task.windowKey)
    }
  }

  getTask(taskId: string) { return this.registry.get(taskId) }
  cancelTask(taskId: string) { const task = this.registry.get(taskId); return task ? this.registry.update(task, { status: 'cancelled', stage: 'cancelled' }) : null }
  activeTaskCount() { return this.registry.activeCount() }
}
