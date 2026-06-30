import type { WindowDescriptor } from '../domain/window-types'
import { getActiveWindowDescriptor, isValidVisibleWxWorkMainWindow } from './window-finder'
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
const FOCUS_CONFIRM_ATTEMPTS = 1
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

function runActivationSteps(window: ManagedWindowLike): void {
  for (const methodName of ACTIVATION_METHODS) {
    const method = window[methodName] as (() => void) | undefined
    if (typeof method !== 'function') continue
    try {
      method()
    } catch {
      // Best effort: continue trying the remaining foreground APIs.
    }
  }
}

export async function activateManagedWindow(
  nativeWindow: ManagedWindowLike | null | undefined,
  _target: WindowDescriptor,
  deps: ActivateManagedWindowDeps = {},
): Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }> {
  if (!isManagedWindowAvailable(nativeWindow)) return { ok: false, errorCode: 'WINDOW_NOT_FOUND' }

  const availableWindow = nativeWindow
  runActivationSteps(availableWindow)

  const sleep = deps.sleep ?? defaultSleep
  const getActiveDescriptor = deps.getActiveWindowDescriptor ?? getActiveWindowDescriptor

  let matchedWindow: WindowDescriptor | null = null
  for (let attempt = 0; attempt < ACTIVATION_MAX_ATTEMPTS; attempt += 1) {
    await sleep(ACTIVATION_POLL_MS)
    const activeDescriptor = await getActiveDescriptor()
    if (isValidVisibleWxWorkMainWindow(activeDescriptor)) {
      matchedWindow = activeDescriptor
      break
    }
  }

  if (!matchedWindow) {
    return { ok: false, errorCode: 'WINDOW_ACTIVATION_FAILED' }
  }

  for (let attempt = 0; attempt < FOCUS_CONFIRM_ATTEMPTS; attempt += 1) {
    await sleep(ACTIVATION_POLL_MS)
    const activeDescriptor = await getActiveDescriptor()
    if (!isValidVisibleWxWorkMainWindow(activeDescriptor)) {
      return { ok: false, errorCode: 'WINDOW_FOCUS_LOST' }
    }
    matchedWindow = activeDescriptor
  }

  return { ok: true, window: matchedWindow }
}

export async function activateWindow(window: WindowDescriptor): Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }> {
  const nativeWindow = findNativeWindow(window)
  if (!nativeWindow) return { ok: false, errorCode: 'WINDOW_NOT_FOUND' }
  return activateManagedWindow(nativeWindow, window)
}
