import { randomUUID } from 'node:crypto'
import type { RuntimeTask, RuntimeTaskRequest } from '../domain/task-types'

export class TaskRegistry {
  private readonly tasks = new Map<string, RuntimeTask>()
  private readonly idempotency = new Map<string, string>()

  createOrGet(request: RuntimeTaskRequest): { task: RuntimeTask; reused: boolean } {
    const existingId = this.idempotency.get(request.idempotencyKey)
    if (existingId) {
      const existing = this.tasks.get(existingId)
      if (existing) return { task: existing, reused: true }
    }
    const now = new Date().toISOString()
    const task: RuntimeTask = {
      id: `task-${randomUUID()}`,
      action: request.action,
      idempotencyKey: request.idempotencyKey,
      requestDigest: request.requestDigest,
      windowKey: request.action === 'paste_draft' ? 'wxwork-main-window' : 'default',
      status: 'queued',
      stage: 'queued',
      createdAt: now,
      updatedAt: now,
      sendAuthorized: false,
      messageSent: false,
    }
    this.tasks.set(task.id, task)
    this.idempotency.set(request.idempotencyKey, task.id)
    return { task, reused: false }
  }

  update(task: RuntimeTask, changes: Partial<RuntimeTask>): RuntimeTask {
    Object.assign(task, changes, { updatedAt: new Date().toISOString() })
    this.tasks.set(task.id, task)
    return task
  }

  get(taskId: string): RuntimeTask | null {
    return this.tasks.get(taskId) ?? null
  }

  activeCount(): number {
    return [...this.tasks.values()].filter((task) => task.status === 'queued' || task.status === 'running').length
  }
}
