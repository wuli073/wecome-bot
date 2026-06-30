import { basename } from 'node:path'
import activeWindow from 'active-win'
import { windowManager } from 'node-window-manager'
import { getElectron } from '../electron-runtime'
import type { Rect, WindowDescriptor } from '../domain/window-types'

export interface WindowSearchCriteria {
  appType: string
  processName?: string
  executablePath?: string
  titleIncludes?: string
}

const WXWORK_ALLOWED_PROCESS_NAMES = new Set(['wxwork', 'wxwork.exe'])
const WXWORK_EXCLUDED_PROCESS_NAMES = new Set(['wxworkweb.exe', 'wechatappex.exe'])
const WXWORK_TITLE_HINTS = ['????', 'wecom', 'wxwork']
const WXWORK_EXACT_WINDOW_TITLE = '????'
const MIN_USABLE_WINDOW_WIDTH = 100
const MIN_USABLE_WINDOW_HEIGHT = 100

function rectFromBounds(bounds: Rect): Rect {
  return {
    x: Number(bounds.x) || 0,
    y: Number(bounds.y) || 0,
    width: Math.max(0, Number(bounds.width) || 0),
    height: Math.max(0, Number(bounds.height) || 0),
  }
}

function getDisplayForBounds(bounds: Rect): { id: string | number; scaleFactor: number } {
  try {
    const display = getElectron().screen.getDisplayMatching(bounds)
    return { id: display.id, scaleFactor: display.scaleFactor }
  } catch {
    return { id: 'unknown', scaleFactor: 1 }
  }
}

function normalizeWindowText(value: string | null | undefined): string {
  return String(value ?? '').trim().toLowerCase()
}

export function normalizeProcessName(processName: string): string {
  return basename(processName || '').trim().toLowerCase()
}

function isAllowedWxWorkProcessName(processName: string): boolean {
  const normalized = normalizeProcessName(processName)
  return Boolean(normalized) && WXWORK_ALLOWED_PROCESS_NAMES.has(normalized)
}

function isExcludedWxWorkProcessName(processName: string): boolean {
  const normalized = normalizeProcessName(processName)
  return Boolean(normalized) && WXWORK_EXCLUDED_PROCESS_NAMES.has(normalized)
}

function titleMatchesWxWork(title: string): boolean {
  const normalizedTitle = normalizeWindowText(title)
  return Boolean(normalizedTitle) && WXWORK_TITLE_HINTS.some((hint) => normalizedTitle.includes(normalizeWindowText(hint)))
}

function hasValidBounds(bounds: Rect | null | undefined): bounds is Rect {
  if (!bounds) return false
  return Number.isFinite(bounds.x)
    && Number.isFinite(bounds.y)
    && Number.isFinite(bounds.width)
    && Number.isFinite(bounds.height)
    && bounds.width >= MIN_USABLE_WINDOW_WIDTH
    && bounds.height >= MIN_USABLE_WINDOW_HEIGHT
}

function appTypeMatches(appType: string, descriptor: WindowDescriptor): boolean {
  const normalized = normalizeWindowText(appType)
  if (!normalized) return true
  if (descriptor.appType === normalized) return true
  if (normalized === 'wework' || normalized === 'wxwork' || normalized === 'wechat_work') {
    return matchesWxWorkWindow(descriptor)
  }

  const normalizedProcessName = normalizeProcessName(descriptor.processName).replace(/\.exe$/i, '')
  const normalizedExecutableName = normalizeProcessName(descriptor.executablePath).replace(/\.exe$/i, '')
  if (normalizedProcessName === normalized || normalizedExecutableName === normalized) return true
  return normalizeWindowText(descriptor.title).includes(normalized)
}

function inferAppType(processName: string, title: string): string {
  if (isAllowedWxWorkProcessName(processName) || isAllowedWxWorkProcessName(title) || titleMatchesWxWork(title)) return 'wework'
  return normalizeProcessName(processName).replace(/\.exe$/i, '') || 'unknown'
}

function formatBounds(bounds: Rect): string {
  return `${bounds.x},${bounds.y},${bounds.width},${bounds.height}`
}

function getWxWorkRejectReason(window: WindowDescriptor | null | undefined): string {
  if (!window) return 'missing_window'
  if (window.isVisible === false) return 'not_visible'
  if (!hasValidBounds(window.clientBounds)) return 'invalid_bounds'
  if (isExcludedWxWorkProcessName(window.processName) || isExcludedWxWorkProcessName(window.executablePath)) return 'excluded_process_name'
  if (!matchesWxWorkWindow(window)) return 'wxwork_mismatch'
  return 'accepted'
}

function logWxWorkWindowInspection(window: WindowDescriptor, accepted: boolean, rejectReason: string): void {
  console.info(
    `WXWork window inspected: handle=${window.windowId} pid=${window.processId} processName=${window.processName || normalizeProcessName(window.executablePath) || 'unknown'} title=${window.title} visible=${window.isVisible} bounds=<${formatBounds(window.clientBounds)}> accepted=${accepted} rejectReason=${rejectReason}`,
  )
}

function hasExactWxWorkTitle(window: WindowDescriptor): boolean {
  return window.title.trim() === WXWORK_EXACT_WINDOW_TITLE
}

function pickPreferredWxWorkWindow(candidates: WindowDescriptor[]): WindowDescriptor | null {
  return candidates.find(hasExactWxWorkTitle) ?? candidates[0] ?? null
}

export function matchesWxWorkWindow(window: Pick<WindowDescriptor, 'title' | 'processName' | 'executablePath'> | null | undefined): boolean {
  if (!window) return false
  if (isExcludedWxWorkProcessName(window.processName) || isExcludedWxWorkProcessName(window.executablePath)) return false
  return isAllowedWxWorkProcessName(window.processName)
    || isAllowedWxWorkProcessName(window.executablePath)
    || titleMatchesWxWork(window.title)
}

export function isUsableWindowDescriptor(window: WindowDescriptor | null | undefined): window is WindowDescriptor {
  if (!window) return false
  if (window.isVisible === false) return false
  return hasValidBounds(window.clientBounds)
}

export function descriptorFromActiveWindow(window: activeWindow.Result): WindowDescriptor {
  const bounds = rectFromBounds(window.bounds)
  const processName = basename(window.owner.path || window.owner.name || '').trim() || window.owner.name || 'unknown'
  const display = getDisplayForBounds(bounds)
  return {
    appType: inferAppType(processName, window.title),
    windowId: String(window.id),
    ownerWindowId: null,
    title: window.title,
    executablePath: window.owner.path || '',
    processName,
    processId: window.owner.processId,
    displayId: display.id,
    boundsLogical: bounds,
    clientBounds: bounds,
    scaleFactor: display.scaleFactor,
    isVisible: bounds.width > 0 && bounds.height > 0,
    isMinimized: bounds.width <= 0 || bounds.height <= 0,
  }
}

export function descriptorFromManagedWindow(window: ReturnType<typeof windowManager.getWindows>[number] | null | undefined): WindowDescriptor | null {
  if (!window) return null
  try {
    if (window.isWindow?.() === false) return null
  } catch {
    // Ignore and continue with best-effort extraction.
  }

  let title = ''
  let bounds: Rect = { x: 0, y: 0, width: 0, height: 0 }
  let visible = false
  let ownerWindowId: string | null = null
  try { title = window.getTitle() } catch { title = '' }
  try { bounds = rectFromBounds(window.getBounds() as Rect) } catch { bounds = { x: 0, y: 0, width: 0, height: 0 } }
  try { visible = window.isVisible() } catch { visible = bounds.width > 0 && bounds.height > 0 }
  try {
    const owner = window.getOwner?.()
    ownerWindowId = owner && typeof owner.id !== 'undefined' ? String(owner.id) : null
  } catch {
    ownerWindowId = null
  }
  const executablePath = window.path || ''
  const processName = basename(executablePath).trim() || 'unknown'
  const display = getDisplayForBounds(bounds)
  return {
    appType: inferAppType(processName, title),
    windowId: String(window.id),
    ownerWindowId,
    title,
    executablePath,
    processName,
    processId: window.processId,
    displayId: display.id,
    boundsLogical: bounds,
    clientBounds: bounds,
    scaleFactor: display.scaleFactor,
    isVisible: visible && bounds.width > 0 && bounds.height > 0,
    isMinimized: bounds.width <= 0 || bounds.height <= 0,
  }
}

export async function discoverWindows(): Promise<WindowDescriptor[]> {
  const managed = windowManager.getWindows()
    .map(descriptorFromManagedWindow)
    .filter((window): window is WindowDescriptor => Boolean(window))
    .filter(isUsableWindowDescriptor)
  if (managed.length) return managed
  const windows = await activeWindow.getOpenWindows({ accessibilityPermission: false, screenRecordingPermission: false })
  return windows.map(descriptorFromActiveWindow).filter(isUsableWindowDescriptor)
}

export async function getActiveWindowDescriptor(): Promise<WindowDescriptor | null> {
  try {
    const managed = descriptorFromManagedWindow(windowManager.getActiveWindow?.())
    if (managed) return managed
  } catch {
    // Fall back to active-win below.
  }
  const window = await activeWindow({ accessibilityPermission: false, screenRecordingPermission: false })
  if (!window) return null
  return descriptorFromActiveWindow(window)
}

export async function getManagedWindowDescriptorById(windowId: string): Promise<WindowDescriptor | null> {
  try {
    const found = windowManager.getWindows().find((candidate) => String(candidate.id) === String(windowId))
    return found ? descriptorFromManagedWindow(found) : null
  } catch {
    return null
  }
}

export function findWindowCandidates(windows: WindowDescriptor[], criteria: WindowSearchCriteria): WindowDescriptor[] {
  return windows.filter((window) => {
    if (!isUsableWindowDescriptor(window)) return false
    if (!appTypeMatches(criteria.appType, window)) return false
    if (criteria.processName && normalizeProcessName(window.processName) !== normalizeProcessName(criteria.processName)) return false
    if (criteria.executablePath && normalizeProcessName(window.executablePath) !== normalizeProcessName(criteria.executablePath)) return false
    if (criteria.titleIncludes && !normalizeWindowText(window.title).includes(normalizeWindowText(criteria.titleIncludes))) return false
    return true
  })
}

export async function findWindows(criteria: WindowSearchCriteria): Promise<WindowDescriptor[]> {
  return findWindowCandidates(await discoverWindows(), criteria)
}

export function isValidVisibleWxWorkMainWindow(window: WindowDescriptor | null | undefined): window is WindowDescriptor {
  return isUsableWindowDescriptor(window) && matchesWxWorkWindow(window)
}

export function collectVisibleWxWorkMainWindows(windows: WindowDescriptor[]): WindowDescriptor[] {
  return windows.filter((window) => {
    const rejectReason = getWxWorkRejectReason(window)
    const accepted = rejectReason === 'accepted'
    logWxWorkWindowInspection(window, accepted, rejectReason)
    return accepted
  })
}

export async function findVisibleWxWorkMainWindows(): Promise<WindowDescriptor[]> {
  return collectVisibleWxWorkMainWindows(await discoverWindows())
}

export function resolvePasteOnlyWxWorkWindow(
  activeDescriptor: WindowDescriptor | null,
  discoveredWindows: WindowDescriptor[],
):
  | { ok: true; window: WindowDescriptor }
  | { ok: false; errorCode: 'TARGET_WINDOW_NOT_FOUND'; candidates: WindowDescriptor[] } {
  if (isValidVisibleWxWorkMainWindow(activeDescriptor)) {
    return { ok: true, window: activeDescriptor }
  }

  const candidates = discoveredWindows.filter(isValidVisibleWxWorkMainWindow)
  const preferred = pickPreferredWxWorkWindow(candidates)
  if (!preferred) {
    return { ok: false, errorCode: 'TARGET_WINDOW_NOT_FOUND', candidates }
  }
  return { ok: true, window: preferred }
}

export function resolveUniqueVisibleWxWorkMainWindow(
  candidates: WindowDescriptor[],
):
  | { ok: true; window: WindowDescriptor }
  | { ok: false; errorCode: 'TARGET_WINDOW_NOT_FOUND'; candidates: WindowDescriptor[] } {
  const visibleCandidates = candidates.filter(isValidVisibleWxWorkMainWindow)
  const preferred = pickPreferredWxWorkWindow(visibleCandidates)
  if (!preferred) return { ok: false, errorCode: 'TARGET_WINDOW_NOT_FOUND', candidates: visibleCandidates }
  return { ok: true, window: preferred }
}

export async function findUniqueVisibleWxWorkMainWindow(): Promise<
  | { ok: true; window: WindowDescriptor }
  | { ok: false; errorCode: 'TARGET_WINDOW_NOT_FOUND'; candidates: WindowDescriptor[] }
> {
  const activeDescriptor = await getActiveWindowDescriptor()
  if (isValidVisibleWxWorkMainWindow(activeDescriptor)) {
    return { ok: true, window: activeDescriptor }
  }
  return resolvePasteOnlyWxWorkWindow(activeDescriptor, await discoverWindows())
}

export function selectSingleWindowCandidate(candidates: WindowDescriptor[]): { ok: true; window: WindowDescriptor } | { ok: false; errorCode: string; candidates: WindowDescriptor[] } {
  if (candidates.length === 1) return { ok: true, window: candidates[0] }
  if (candidates.length > 1) return { ok: false, errorCode: 'WINDOW_CANDIDATE_AMBIGUOUS', candidates }
  return { ok: false, errorCode: 'WINDOW_NOT_FOUND', candidates }
}

export function isLikelyMainWindow(window: WindowDescriptor, appType: string): boolean {
  return isUsableWindowDescriptor(window) && appTypeMatches(appType, window)
}
