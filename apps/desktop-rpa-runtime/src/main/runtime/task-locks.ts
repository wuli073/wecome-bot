export class ExecutionLaneTaskQueue {
  private readonly active = new Map<string, string>()
  private readonly queued = new Map<string, string[]>()

  startOrQueue(executionLaneKey: string, taskId: string): 'running' | 'queued' {
    if (!this.active.has(executionLaneKey)) {
      this.active.set(executionLaneKey, taskId)
      return 'running'
    }
    const pending = this.queued.get(executionLaneKey) ?? []
    pending.push(taskId)
    this.queued.set(executionLaneKey, pending)
    return 'queued'
  }

  finish(executionLaneKey: string, taskId: string): string | null {
    if (this.active.get(executionLaneKey) !== taskId) {
      return null
    }
    const pending = this.queued.get(executionLaneKey) ?? []
    while (pending.length > 0) {
      const nextTaskId = pending.shift()
      if (!nextTaskId) continue
      if (pending.length === 0) this.queued.delete(executionLaneKey)
      else this.queued.set(executionLaneKey, pending)
      this.active.set(executionLaneKey, nextTaskId)
      return nextTaskId
    }
    this.active.delete(executionLaneKey)
    this.queued.delete(executionLaneKey)
    return null
  }

  cancelQueued(executionLaneKey: string, taskId: string): boolean {
    const pending = this.queued.get(executionLaneKey)
    if (!pending || pending.length === 0) {
      return false
    }
    const index = pending.indexOf(taskId)
    if (index < 0) {
      return false
    }
    pending.splice(index, 1)
    if (pending.length === 0) this.queued.delete(executionLaneKey)
    else this.queued.set(executionLaneKey, pending)
    return true
  }

  isActive(executionLaneKey: string, taskId?: string): boolean {
    if (taskId === undefined) {
      return this.active.has(executionLaneKey)
    }
    return this.active.get(executionLaneKey) === taskId
  }
}
