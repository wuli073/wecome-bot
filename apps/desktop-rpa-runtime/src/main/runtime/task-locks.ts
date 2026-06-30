export class PerWindowTaskLock {
  private readonly locked = new Set<string>()

  acquire(windowKey: string): boolean {
    if (this.locked.has(windowKey)) return false
    this.locked.add(windowKey)
    return true
  }

  release(windowKey: string): void {
    this.locked.delete(windowKey)
  }

  isLocked(windowKey: string): boolean {
    return this.locked.has(windowKey)
  }
}
