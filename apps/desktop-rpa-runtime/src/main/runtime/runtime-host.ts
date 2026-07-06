import type { RuntimeTaskRequest } from '../domain/task-types'
import { RuntimeHttpError } from '../domain/error-types'
import type { PasteVerificationProvider } from '../input/paste-verification'
import { ExecutionLaneTaskQueue } from './task-locks'
import { TaskRegistry } from './task-registry'
import { TaskRunner, type TaskRunnerOptions } from './task-runner'

export class RuntimeHost {
  readonly registry = new TaskRegistry()
  readonly locks = new ExecutionLaneTaskQueue()
  readonly runner: TaskRunner
  private readonly cancelledTaskIds = new Set<string>()
  private readonly requestByTaskId = new Map<string, RuntimeTaskRequest>()
  private readonly taskPromises = new Map<string, Promise<void>>()
  private shuttingDown = false

  constructor(options: TaskRunnerOptions = {}, verifierProvider?: PasteVerificationProvider) {
    this.runner = new TaskRunner({
      ...options,
      pasteVerificationProvider: verifierProvider ?? options.pasteVerificationProvider,
    })
  }

  async createTask(request: RuntimeTaskRequest) {
    if (this.shuttingDown) {
      throw new RuntimeHttpError(503, 'RUNTIME_SHUTTING_DOWN', 'Runtime host is shutting down')
    }
    const { task, reused } = this.registry.createOrGet(request)
    if (reused) return task
    this.requestByTaskId.set(task.id, request)
    if (this.locks.startOrQueue(task.executionLaneKey, task.id) === 'running') {
      this.startTask(task.id)
      const current = this.registry.get(task.id)
      if (!current) throw new Error(`Task disappeared after creation: ${task.id}`)
      return current
    }
    return this.registry.update(task, { status: 'queued', stage: 'queued_for_execution_lane' })
  }

  getTask(taskId: string) { return this.registry.get(taskId) }
  isShuttingDown() { return this.shuttingDown }

  cancelTask(taskId: string) {
    const task = this.registry.get(taskId)
    if (!task) return null
    if (task.status !== 'queued' && task.status !== 'running') return task
    if (this.locks.cancelQueued(task.executionLaneKey, task.id)) {
      this.requestByTaskId.delete(task.id)
      return this.registry.update(task, { status: 'cancelled', stage: 'cancelled' })
    }
    this.cancelledTaskIds.add(task.id)
    return this.registry.update(task, { status: 'running', stage: 'cancelling' })
  }

  activeTaskCount() { return this.registry.activeCount() }

  async getRuntimeStatusPatch() {
    const pasteVerification = await this.runner.refreshPasteVerificationCapability(false)
    return {
      activeTaskCount: this.activeTaskCount(),
      pasteVerification,
    }
  }

  async shutdown(): Promise<void> {
    this.shuttingDown = true
    for (const task of this.registry.all()) {
      if (task.status === 'queued') {
        this.requestByTaskId.delete(task.id)
        this.locks.cancelQueued(task.executionLaneKey, task.id)
        this.registry.update(task, { status: 'interrupted', stage: 'runtime_shutdown' })
      } else if (task.status === 'running') {
        this.cancelledTaskIds.add(task.id)
      }
    }
    await Promise.allSettled(this.taskPromises.values())
  }

  private startTask(taskId: string): void {
    const task = this.registry.get(taskId)
    const request = this.requestByTaskId.get(taskId)
    if (!task || !request) return
    if (this.cancelledTaskIds.has(task.id) || task.status === 'cancelled') {
      this.cancelledTaskIds.delete(task.id)
      this.requestByTaskId.delete(task.id)
      this.registry.update(task, { status: 'cancelled', stage: 'cancelled' })
      this.startNextTask(task.executionLaneKey, task.id)
      return
    }

    this.registry.update(task, { status: 'running', stage: 'running' })
    const promise = this.executeTask(task.id, request)
      .finally(() => {
        this.taskPromises.delete(task.id)
        this.cancelledTaskIds.delete(task.id)
        this.requestByTaskId.delete(task.id)
        this.startNextTask(task.executionLaneKey, task.id)
      })
    this.taskPromises.set(task.id, promise)
  }

  private async executeTask(taskId: string, request: RuntimeTaskRequest): Promise<void> {
    const task = this.registry.get(taskId)
    if (!task) return
    try {
      const result = await this.runner.run(request, {
        isCancelled: () => this.cancelledTaskIds.has(taskId),
      })
      const latest = this.registry.get(taskId)
      if (!latest) return
      const cancelledDuringExecution = this.cancelledTaskIds.has(taskId)
      if (cancelledDuringExecution) {
        this.registry.update(latest, {
          status: 'cancelled',
          stage: 'cancelled',
          errorCode: 'TASK_CANCELLED',
          result: {
            ...(result ?? {}),
            status: 'cancelled',
            stage: 'cancelled',
            errorCode: 'TASK_CANCELLED',
          },
        })
        return
      }
      this.registry.update(latest, {
        status: (result.status as never) ?? 'failed',
        stage: String(result.stage ?? 'completed'),
        sendAuthorized: Boolean(result.sendAuthorized),
        messageSent: Boolean(result.messageSent),
        clipboardRestoreFailed: Boolean(result.clipboardRestoreFailed),
        errorCode: typeof result.errorCode === 'string' ? result.errorCode : undefined,
        result,
      })
    } catch (error) {
      const latest = this.registry.get(taskId)
      if (!latest) return
      const errorCode = error instanceof Error && error.message ? error.message : 'TASK_FAILED'
      this.registry.update(latest, {
        status: errorCode === 'TASK_CANCELLED' ? 'cancelled' : 'failed',
        stage: errorCode === 'TASK_CANCELLED' ? 'cancelled' : 'failed',
        errorCode,
        result: {
          status: errorCode === 'TASK_CANCELLED' ? 'cancelled' : 'failed',
          stage: errorCode === 'TASK_CANCELLED' ? 'cancelled' : 'failed',
          errorCode,
        },
      })
    }
  }

  private startNextTask(executionLaneKey: string, completedTaskId: string): void {
    const nextTaskId = this.locks.finish(executionLaneKey, completedTaskId)
    if (this.shuttingDown || !nextTaskId) return
    this.startTask(nextTaskId)
  }
}
