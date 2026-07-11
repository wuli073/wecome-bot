import { app } from 'electron'

export function ensureSingleInstance(): void {
  const lockAcquired = app.requestSingleInstanceLock()
  if (!lockAcquired) {
    app.exit(0)
  }
}
