import type { RuntimeTaskRequest } from '../domain/task-types'
import type { PasteVerificationProvider } from '../input/paste-verification'
import { PerWindowTaskLock } from './task-locks'
import { TaskRegistry } from './task-registry'
import { TaskRunner, type TaskRunnerOptions } from './task-runner'

export class RuntimeHost {
  readonly registry = new TaskRegistry()
  readonly locks = new PerWindowTaskLock()
  readonly runner: TaskRunner
  private readonly cancelledTaskIds = new Set<string>()

  constructor(options: TaskRunnerOptions = {}, verifierProvider?: PasteVerificationProvider) {
    this.runner = new TaskRunner({
      ...options,
      pasteVerificationProvider: verifierProvider ?? options.pasteVerificationProvider,
    })
  }

  async createTask(request: RuntimeTaskRequest) {
    const { task, reused } = this.registry.createOrGet(request)
    if (reused) return task
    if (!this.locks.acquire(task.windowKey)) {
      return this.registry.update(task, { status: 'queued', stage: 'queued_for_window_lock' })
    }
    try {
      this.registry.update(task, { status: 'running', stage: 'running' })
      const result = await this.runner.run(request, {
        isCancelled: () => this.cancelledTaskIds.has(task.id),
      })
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
      this.cancelledTaskIds.delete(task.id)
      this.locks.release(task.windowKey)
    }
  }

  getTask(taskId: string) { return this.registry.get(taskId) }
  cancelTask(taskId: string) {
    const task = this.registry.get(taskId)
    if (!task) return null
    this.cancelledTaskIds.add(task.id)
    return this.registry.update(task, { status: 'cancelled', stage: 'cancelled' })
  }
  activeTaskCount() { return this.registry.activeCount() }
  async getRuntimeStatusPatch() {
    const pasteVerification = await this.runner.refreshPasteVerificationCapability(false)
    return {
      activeTaskCount: this.activeTaskCount(),
      pasteVerification,
    }
  }
}
