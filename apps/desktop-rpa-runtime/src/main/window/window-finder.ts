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

export interface CanonicalWindowCandidate {
  hwnd: string
  rootHwnd: string
  ownerHwnd: string
  processId: number
  processName: string
  executableName: string
  title: string
  className: string
  visible: boolean
  minimized: boolean
  source: string
  accepted: boolean
  rejectionReason: string | null
}

export interface WindowRejectionSummary {
  reason: string
  count: number
}

export interface WxWorkWindowSelectionDiagnostics {
  candidateCountBeforeFilter: number
  canonicalCandidateCount: number
  candidateCountAfterFilter: number
  rejectedCandidateCount: number
  selectedWindow: CanonicalWindowCandidate | null
  candidates: CanonicalWindowCandidate[]
  rejectionReasons: WindowRejectionSummary[]
}

type WindowSelectionResult =
  | {
      ok: true
      window: WindowDescriptor
      candidates: WindowDescriptor[]
      diagnostics: WxWorkWindowSelectionDiagnostics
    }
  | {
      ok: false
      errorCode: 'TARGET_WINDOW_NOT_FOUND' | 'TARGET_WINDOW_AMBIGUOUS'
      candidates: WindowDescriptor[]
      diagnostics: WxWorkWindowSelectionDiagnostics
    }

type CanonicalWindowEntry = {
  descriptor: WindowDescriptor
  candidate: CanonicalWindowCandidate
}

const WXWORK_ALLOWED_PROCESS_NAMES = new Set(['wxwork', 'wxwork.exe'])
const WXWORK_EXCLUDED_PROCESS_NAMES = new Set(['wxworkweb.exe', 'wechatappex.exe'])
const WXWORK_TITLE_HINTS = ['企业微信', 'wecom', 'wxwork']
const WXWORK_STABLE_MAIN_WINDOW_TITLES = new Set(['企业微信', 'wecom', 'wxwork'])
const MIN_USABLE_WINDOW_WIDTH = 100
const MIN_USABLE_WINDOW_HEIGHT = 100
const DIAGNOSTIC_CANDIDATE_LIMIT = 8

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

function normalizeHandle(value: string | number | null | undefined): string {
  const normalized = String(value ?? '').trim()
  return normalized.length > 0 ? normalized : '0'
}

function isZeroHandle(value: string | number | null | undefined): boolean {
  return normalizeHandle(value) === '0'
}

function normalizeTitle(value: string | null | undefined): string {
  return String(value ?? '').trim()
}

function normalizeClassName(value: string | null | undefined): string {
  return String(value ?? '').trim()
}

function normalizeSource(value: string | null | undefined): string {
  return String(value ?? '').trim() || 'unknown'
}

function normalizeExecutableName(executablePath: string | null | undefined, processName: string | null | undefined): string {
  return normalizeProcessName(executablePath || processName || '')
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

function hasStableWxWorkMainTitle(title: string): boolean {
  return WXWORK_STABLE_MAIN_WINDOW_TITLES.has(normalizeWindowText(title))
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

function getManagedWindowRootId(window: ReturnType<typeof windowManager.getWindows>[number] | null | undefined): string | null {
  const visited = new Set<string>()
  let current = window
  let currentId = current && typeof current.id !== 'undefined' ? normalizeHandle(current.id) : null
  while (current) {
    if (!currentId || currentId === '0' || visited.has(currentId)) {
      break
    }
    visited.add(currentId)
    try {
      const owner = current.getOwner?.()
      if (!owner || typeof owner.id === 'undefined') return currentId
      const ownerId = normalizeHandle(owner.id)
      if (ownerId === '0' || ownerId === currentId) return currentId
      current = owner as ReturnType<typeof windowManager.getWindows>[number]
      currentId = ownerId
    } catch {
      return currentId
    }
  }
  return currentId
}

function mergeSources(a: string | null | undefined, b: string | null | undefined): string {
  const values = new Set(
    [a, b]
      .map(normalizeSource)
      .filter((value) => value.length > 0),
  )
  return [...values].join('|')
}

function preferString(current: string, incoming: string): string {
  return current.length >= incoming.length ? current : incoming
}

function preferHandle(current: string, incoming: string): string {
  return !isZeroHandle(current) ? current : incoming
}

function preferDescriptor(primary: WindowDescriptor, incoming: WindowDescriptor): WindowDescriptor {
  return {
    ...primary,
    appType: primary.appType || incoming.appType,
    ownerWindowId: preferHandle(normalizeHandle(primary.ownerWindowId), normalizeHandle(incoming.ownerWindowId)),
    rootWindowId: preferHandle(normalizeHandle(primary.rootWindowId), normalizeHandle(incoming.rootWindowId)),
    title: preferString(normalizeTitle(primary.title), normalizeTitle(incoming.title)),
    executablePath: preferString(String(primary.executablePath || ''), String(incoming.executablePath || '')),
    processName: preferString(String(primary.processName || ''), String(incoming.processName || '')),
    displayId: primary.displayId ?? incoming.displayId,
    boundsLogical: hasValidBounds(primary.boundsLogical) ? primary.boundsLogical : incoming.boundsLogical,
    clientBounds: hasValidBounds(primary.clientBounds) ? primary.clientBounds : incoming.clientBounds,
    scaleFactor: primary.scaleFactor || incoming.scaleFactor,
    isVisible: primary.isVisible || incoming.isVisible,
    isMinimized: primary.isMinimized && incoming.isMinimized,
    className: preferString(normalizeClassName(primary.className), normalizeClassName(incoming.className)) || null,
    source: mergeSources(primary.source, incoming.source),
  }
}

function descriptorToCanonicalCandidate(window: WindowDescriptor): CanonicalWindowCandidate {
  const hwnd = normalizeHandle(window.windowId)
  const ownerHwnd = normalizeHandle(window.ownerWindowId)
  const rootHwnd = normalizeHandle(window.rootWindowId ?? window.ownerWindowId ?? window.windowId)
  return {
    hwnd,
    rootHwnd: isZeroHandle(rootHwnd) ? hwnd : rootHwnd,
    ownerHwnd,
    processId: Number(window.processId) || 0,
    processName: normalizeProcessName(window.processName),
    executableName: normalizeExecutableName(window.executablePath, window.processName),
    title: normalizeTitle(window.title),
    className: normalizeClassName(window.className),
    visible: window.isVisible !== false,
    minimized: Boolean(window.isMinimized),
    source: normalizeSource(window.source),
    accepted: false,
    rejectionReason: null,
  }
}

function evaluateWxWorkCandidate(candidate: CanonicalWindowCandidate): string | null {
  if (isZeroHandle(candidate.hwnd)) return 'invalid_hwnd'
  if (candidate.visible === false) return 'not_visible'
  if (candidate.minimized) return 'minimized'
  if (!candidate.processId) return 'missing_process_id'
  if (isExcludedWxWorkProcessName(candidate.processName) || isExcludedWxWorkProcessName(candidate.executableName)) return 'excluded_process_name'
  if (!isAllowedWxWorkProcessName(candidate.processName) && !isAllowedWxWorkProcessName(candidate.executableName)) return 'process_mismatch'
  if (candidate.title.length === 0) return 'empty_title'
  if (!hasStableWxWorkMainTitle(candidate.title)) return 'title_mismatch'
  if (!isZeroHandle(candidate.ownerHwnd)) return 'owned_window'
  if (candidate.rootHwnd !== candidate.hwnd) return 'non_root_window'
  return null
}

function mergeCanonicalEntries(entries: CanonicalWindowEntry[]): CanonicalWindowEntry[] {
  const byHwnd = new Map<string, CanonicalWindowEntry>()
  for (const entry of entries) {
    const existing = byHwnd.get(entry.candidate.hwnd)
    if (!existing) {
      byHwnd.set(entry.candidate.hwnd, entry)
      continue
    }
    const descriptor = preferDescriptor(existing.descriptor, entry.descriptor)
    const mergedCandidate = descriptorToCanonicalCandidate(descriptor)
    mergedCandidate.source = mergeSources(existing.candidate.source, entry.candidate.source)
    byHwnd.set(entry.candidate.hwnd, { descriptor, candidate: mergedCandidate })
  }
  return [...byHwnd.values()]
}

function summarizeRejectionReasons(candidates: CanonicalWindowCandidate[]): WindowRejectionSummary[] {
  const counts = new Map<string, number>()
  for (const candidate of candidates) {
    if (!candidate.rejectionReason) continue
    counts.set(candidate.rejectionReason, (counts.get(candidate.rejectionReason) ?? 0) + 1)
  }
  return [...counts.entries()].map(([reason, count]) => ({ reason, count }))
}

function trimDiagnosticCandidates(candidates: CanonicalWindowCandidate[]): CanonicalWindowCandidate[] {
  return candidates.slice(0, DIAGNOSTIC_CANDIDATE_LIMIT).map((candidate) => ({ ...candidate }))
}

function buildWindowSelectionDiagnostics(entries: CanonicalWindowEntry[]): {
  diagnostics: WxWorkWindowSelectionDiagnostics
  acceptedEntries: CanonicalWindowEntry[]
} {
  const mergedEntries = mergeCanonicalEntries(entries)
  const byRoot = new Map<string, CanonicalWindowEntry>()
  const inspected = mergedEntries.map((entry) => {
    const candidate = { ...entry.candidate }
    candidate.rejectionReason = evaluateWxWorkCandidate(candidate)
    candidate.accepted = candidate.rejectionReason === null
    if (candidate.accepted) {
      const rootKey = `${candidate.processId}:${candidate.rootHwnd}`
      const existing = byRoot.get(rootKey)
      if (existing) {
        candidate.accepted = false
        candidate.rejectionReason = 'duplicate_root_window'
      } else {
        byRoot.set(rootKey, entry)
      }
    }
    return { descriptor: entry.descriptor, candidate }
  })

  const acceptedEntries = inspected.filter((entry) => entry.candidate.accepted)
  const selectedWindow = acceptedEntries.length === 1 ? acceptedEntries[0].candidate : null
  const diagnostics: WxWorkWindowSelectionDiagnostics = {
    candidateCountBeforeFilter: entries.length,
    canonicalCandidateCount: mergedEntries.length,
    candidateCountAfterFilter: acceptedEntries.length,
    rejectedCandidateCount: inspected.length - acceptedEntries.length,
    selectedWindow,
    candidates: trimDiagnosticCandidates(inspected.map((entry) => entry.candidate)),
    rejectionReasons: summarizeRejectionReasons(inspected.map((entry) => entry.candidate)),
  }

  return {
    diagnostics,
    acceptedEntries,
  }
}

function buildSelectionResult(windows: WindowDescriptor[]): WindowSelectionResult {
  const entries = windows.map((descriptor) => ({
    descriptor,
    candidate: descriptorToCanonicalCandidate(descriptor),
  }))
  const { diagnostics, acceptedEntries } = buildWindowSelectionDiagnostics(entries)
  const acceptedWindows = acceptedEntries.map((entry) => entry.descriptor)

  if (acceptedWindows.length <= 0) {
    return {
      ok: false,
      errorCode: 'TARGET_WINDOW_NOT_FOUND',
      candidates: acceptedWindows,
      diagnostics,
    }
  }
  if (acceptedWindows.length > 1) {
    return {
      ok: false,
      errorCode: 'TARGET_WINDOW_AMBIGUOUS',
      candidates: acceptedWindows,
      diagnostics,
    }
  }
  return {
    ok: true,
    window: acceptedWindows[0],
    candidates: acceptedWindows,
    diagnostics,
  }
}

function withRootWindowId(window: WindowDescriptor): WindowDescriptor {
  return {
    ...window,
    ownerWindowId: normalizeHandle(window.ownerWindowId),
    rootWindowId: normalizeHandle(window.rootWindowId ?? window.ownerWindowId ?? window.windowId),
  }
}

export function matchesWxWorkWindow(window: Pick<WindowDescriptor, 'title' | 'processName' | 'executablePath'> | null | undefined): boolean {
  if (!window) return false
  if (isExcludedWxWorkProcessName(window.processName) || isExcludedWxWorkProcessName(window.executablePath)) return false
  return isAllowedWxWorkProcessName(window.processName)
    || isAllowedWxWorkProcessName(window.executablePath)
    || hasStableWxWorkMainTitle(window.title)
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
  const windowId = normalizeHandle(window.id)
  return {
    appType: inferAppType(processName, window.title),
    windowId,
    ownerWindowId: '0',
    rootWindowId: windowId,
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
    className: null,
    source: 'active-win',
  }
}

export function descriptorFromManagedWindow(window: ReturnType<typeof windowManager.getWindows>[number] | null | undefined): WindowDescriptor | null {
  if (!window) return null
  try {
    if (window.isWindow?.() === false) return null
  } catch {
    return null
  }

  let title = ''
  let bounds: Rect = { x: 0, y: 0, width: 0, height: 0 }
  let visible = false
  let ownerWindowId = '0'
  try { title = window.getTitle() } catch { title = '' }
  try { bounds = rectFromBounds(window.getBounds() as Rect) } catch { bounds = { x: 0, y: 0, width: 0, height: 0 } }
  try { visible = window.isVisible() } catch { visible = bounds.width > 0 && bounds.height > 0 }
  try {
    const owner = window.getOwner?.()
    ownerWindowId = normalizeHandle(owner && typeof owner.id !== 'undefined' ? owner.id : 0)
  } catch {
    ownerWindowId = '0'
  }
  const executablePath = window.path || ''
  const processName = basename(executablePath).trim() || 'unknown'
  const display = getDisplayForBounds(bounds)
  return {
    appType: inferAppType(processName, title),
    windowId: normalizeHandle(window.id),
    ownerWindowId,
    rootWindowId: normalizeHandle(getManagedWindowRootId(window) ?? window.id),
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
    className: null,
    source: 'node-window-manager',
  }
}

export async function discoverWindows(): Promise<WindowDescriptor[]> {
  const managed = windowManager.getWindows()
    .map(descriptorFromManagedWindow)
    .filter((window): window is WindowDescriptor => Boolean(window))
    .filter(isUsableWindowDescriptor)
    .map(withRootWindowId)

  let active: WindowDescriptor[] = []
  try {
    active = (await activeWindow.getOpenWindows({ accessibilityPermission: false, screenRecordingPermission: false }))
      .map(descriptorFromActiveWindow)
      .filter(isUsableWindowDescriptor)
      .map(withRootWindowId)
  } catch {
    active = []
  }

  return [...managed, ...active]
}

export async function getActiveWindowDescriptor(): Promise<WindowDescriptor | null> {
  try {
    const managed = descriptorFromManagedWindow(windowManager.getActiveWindow?.())
    if (managed) return withRootWindowId(managed)
  } catch {
    // Fall back to active-win below.
  }
  const window = await activeWindow({ accessibilityPermission: false, screenRecordingPermission: false })
  if (!window) return null
  return withRootWindowId(descriptorFromActiveWindow(window))
}

export async function getManagedWindowDescriptorById(windowId: string): Promise<WindowDescriptor | null> {
  try {
    const found = windowManager.getWindows().find((candidate) => String(candidate.id) === String(windowId))
    const descriptor = found ? descriptorFromManagedWindow(found) : null
    return descriptor ? withRootWindowId(descriptor) : null
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
  if (!isUsableWindowDescriptor(window)) return false
  return evaluateWxWorkCandidate(descriptorToCanonicalCandidate(withRootWindowId(window))) === null
}

export function inspectWxWorkWindowCandidates(windows: WindowDescriptor[]): WxWorkWindowSelectionDiagnostics {
  return buildSelectionResult(windows).diagnostics
}

export function collectVisibleWxWorkMainWindows(windows: WindowDescriptor[]): WindowDescriptor[] {
  const result = buildSelectionResult(windows)
  return result.candidates
}

export async function findVisibleWxWorkMainWindows(): Promise<WindowDescriptor[]> {
  return collectVisibleWxWorkMainWindows(await discoverWindows())
}

export function resolvePasteOnlyWxWorkWindow(
  activeDescriptor: WindowDescriptor | null,
  discoveredWindows: WindowDescriptor[],
): WindowSelectionResult {
  const windows = [...discoveredWindows]
  if (activeDescriptor) {
    windows.push(withRootWindowId(activeDescriptor))
  }
  return buildSelectionResult(windows)
}

export function resolveUniqueVisibleWxWorkMainWindow(
  candidates: WindowDescriptor[],
): WindowSelectionResult {
  return buildSelectionResult(candidates)
}

export async function findUniqueVisibleWxWorkMainWindow(): Promise<WindowSelectionResult> {
  const activeDescriptor = await getActiveWindowDescriptor()
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
