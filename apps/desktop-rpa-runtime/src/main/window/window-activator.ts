import type { WindowDescriptor } from '../domain/window-types'
import { getActiveWindowDescriptor, matchesWxWorkWindow } from './window-finder'
import { windowManager } from 'node-window-manager'

type ManagedWindowLike = {
  id?: number | string
  isWindow?: () => boolean
  isVisible?: () => boolean
  restore?: () => void
  show?: () => void
  showWindow?: () => void
  focus?: () => void
  setForeground?: () => void
  activate?: () => void
  bringToTop?: () => void
}

interface ActivateManagedWindowDeps {
  sleep?: (ms: number) => Promise<void>
  getActiveWindowDescriptor?: () => Promise<WindowDescriptor | null>
}

const ACTIVATION_POLL_MS = 60
const ACTIVATION_MAX_ATTEMPTS = 6
const ACTIVATION_METHODS = [
  'restore',
  'show',
  'showWindow',
  'focus',
  'setForeground',
  'activate',
  'bringToTop',
] as const

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function findNativeWindow(target: WindowDescriptor): ManagedWindowLike | undefined {
  return windowManager.getWindows().find((window) => String(window.id) === String(target.windowId))
}

function isManagedWindowAvailable(window: ManagedWindowLike | null | undefined): window is ManagedWindowLike {
  if (!window) return false
  try {
    if (window.isWindow?.() === false) return false
  } catch {
    return false
  }
  try {
    if (window.isVisible?.() === false) return false
  } catch {
    return false
  }
  return true
}

function sanitizeForLog(value: unknown): string {
  return String(value ?? '').replace(/[\r\n]+/g, ' ').trim()
}

function logActivationTarget(target: WindowDescriptor): void {
  console.info(
    `event=window_activation_target targetId=${sanitizeForLog(target.windowId)} targetProcessId=${sanitizeForLog(target.processId)} targetProcessName=${sanitizeForLog(target.processName || 'unknown')} targetTitleLength=${target.title.length}`,
  )
}

function logActivationMethod(method: string, available: boolean, ok: boolean, errorName?: string): void {
  console.info(
    `event=window_activation_method method=${sanitizeForLog(method)} available=${available} ok=${ok} errorName=${sanitizeForLog(errorName ?? '')}`,
  )
}

function logActivationPoll(attempt: number, activeDescriptor: WindowDescriptor | null, matched: boolean): void {
  console.info(
    `event=window_activation_poll attempt=${attempt} matched=${matched} activeId=${sanitizeForLog(activeDescriptor?.windowId ?? '')} activeProcessId=${sanitizeForLog(activeDescriptor?.processId ?? '')} activeProcessName=${sanitizeForLog(activeDescriptor?.processName ?? '')} activeTitleLength=${activeDescriptor?.title.length ?? 0}`,
  )
}

function isWxWorkActiveWindow(window: WindowDescriptor | null | undefined): window is WindowDescriptor {
  return Boolean(window) && matchesWxWorkWindow(window)
}

async function findMatchingActiveWindow(
  getActiveDescriptor: () => Promise<WindowDescriptor | null>,
  sleep: (ms: number) => Promise<void>,
): Promise<WindowDescriptor | null> {
  for (let attempt = 0; attempt < ACTIVATION_MAX_ATTEMPTS; attempt += 1) {
    if (attempt > 0) {
      await sleep(ACTIVATION_POLL_MS)
    }
    const activeDescriptor = await getActiveDescriptor()
    const matched = isWxWorkActiveWindow(activeDescriptor)
    logActivationPoll(attempt, activeDescriptor, matched)
    if (matched) {
      return activeDescriptor
    }
  }

  return null
}

function runActivationSteps(window: ManagedWindowLike): void {
  for (const methodName of ACTIVATION_METHODS) {
    const method = window[methodName] as (() => void) | undefined
    if (typeof method !== 'function') {
      logActivationMethod(methodName, false, false)
      continue
    }
    try {
      method.call(window)
      logActivationMethod(methodName, true, true)
    } catch (error) {
      logActivationMethod(methodName, true, false, error instanceof Error ? error.name : 'UnknownError')
    }
  }
}

export async function activateManagedWindow(
  nativeWindow: ManagedWindowLike | null | undefined,
  _target: WindowDescriptor,
  deps: ActivateManagedWindowDeps = {},
): Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }> {
  if (!isManagedWindowAvailable(nativeWindow)) return { ok: false, errorCode: 'WINDOW_NOT_FOUND' }

  logActivationTarget(_target)

  const sleep = deps.sleep ?? defaultSleep
  const getActiveDescriptor = deps.getActiveWindowDescriptor ?? getActiveWindowDescriptor
  const activeBeforeActivation = await getActiveDescriptor()
  if (isWxWorkActiveWindow(activeBeforeActivation)) {
    logActivationPoll(0, activeBeforeActivation, true)
    return { ok: true, window: activeBeforeActivation }
  }

  const availableWindow = nativeWindow
  runActivationSteps(availableWindow)
  const matchedWindow = await findMatchingActiveWindow(getActiveDescriptor, sleep)

  if (!matchedWindow) {
    return { ok: false, errorCode: 'WINDOW_ACTIVATION_FAILED' }
  }

  return { ok: true, window: matchedWindow }
}

export async function activateWindow(window: WindowDescriptor): Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }> {
  const nativeWindow = findNativeWindow(window)
  if (!nativeWindow) return { ok: false, errorCode: 'WINDOW_NOT_FOUND' }
  return activateManagedWindow(nativeWindow, window)
}
