import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import { ClipboardController, type ClipboardAdapter } from '../src/main/input/clipboard-controller'
import type { InputDriver } from '../src/main/input/mouse-controller'
import { runPasteOnlyTask } from '../src/main/input/paste-controller'
import {
  buildFileClipboardHelperArgs,
  buildFileClipboardHelperPayload,
  computeAttachmentPostPasteDelayMs,
  encodePowerShellCommandUtf16Le,
  parseFileClipboardHelperOutput,
  WindowsFileClipboardController,
} from '../src/main/input/file-clipboard-controller'
import { RuntimeHost } from '../src/main/runtime/runtime-host'
import * as windowActivator from '../src/main/window/window-activator'
import * as windowFinder from '../src/main/window/window-finder'
import type { RuntimeAttachmentPayload } from '../src/main/domain/task-types'
import type { WindowDescriptor } from '../src/main/domain/window-types'

const wxworkWindow: WindowDescriptor = {
  appType: 'wework',
  windowId: 'w1',
  ownerWindowId: '0',
  rootWindowId: 'w1',
  title: '企业微信',
  executablePath: 'C:/Program Files/WXWork/WXWork.exe',
  processName: 'WXWork.exe',
  processId: 123,
  displayId: 1,
  boundsLogical: { x: 0, y: 0, width: 1000, height: 800 },
  clientBounds: { x: 0, y: 0, width: 1000, height: 800 },
  scaleFactor: 1,
  isVisible: true,
  isMinimized: false,
  className: 'Qt51514QWindowIcon',
  source: 'node-window-manager',
}

class RecordingInputDriver implements InputDriver {
  readonly events: Array<{ type: string; payload: unknown }> = []
  async click(point: { x: number; y: number }): Promise<void> { this.events.push({ type: 'click', payload: point }) }
  async hotkey(keys: string[]): Promise<void> { this.events.push({ type: 'hotkey', payload: keys }) }
  async typeText(text: string): Promise<void> { this.events.push({ type: 'typeText', payload: text }) }
}

class RecordingFileClipboardController {
  readonly writes: RuntimeAttachmentPayload[][] = []
  async writeFiles(files: RuntimeAttachmentPayload[]): Promise<void> {
    this.writes.push(files)
  }
}

class FakeChildProcess extends EventEmitter {
  stdout = new EventEmitter()
  stderr = new EventEmitter()
  stdinWrites: Buffer[] = []
  stdinEnded = false
  killed = false
  stdin = {
    write: (chunk: Buffer) => {
      this.stdinWrites.push(Buffer.from(chunk))
      return true
    },
    end: () => {
      this.stdinEnded = true
    },
  }
  kill() {
    this.killed = true
    this.emit('close', null)
    return true
  }
}

function sha256(text: string) {
  return createHash('sha256').update(text, 'utf8').digest('hex')
}

function fakeClipboardAdapter(formats: string[], data: Record<string, string> = {}): ClipboardAdapter {
  return {
    availableFormats: () => formats,
    readText: () => data.text ?? '',
    readHTML: () => data.html ?? '',
    readRTF: () => data.rtf ?? '',
    readImage: () => ({ isEmpty: () => !data.image, toDataURL: () => data.image ?? '' }),
    write: (next) => { Object.assign(data, next) },
    writeText: (text) => { data.text = text },
  }
}

test('WXWork candidate rules accept visible windows with valid bounds and exclude helper executables', () => {
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow(wxworkWindow), true)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, executablePath: '', processName: 'WXWork' }), true)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, executablePath: 'D:/WXWork/WXWork.exe', processName: 'unknown' }), true)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, executablePath: '', processName: '', title: 'Customer A - wecom' }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, ownerWindowId: 'parent' }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, executablePath: 'C:/Program Files/WXWork/WXWorkWeb.exe', processName: 'WXWorkWeb.exe' }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, executablePath: 'C:/Program Files/WXWork/WeChatAppEx.exe', processName: 'WeChatAppEx.exe' }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, isVisible: false }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, clientBounds: { x: 0, y: 0, width: 99, height: 800 } }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, clientBounds: { x: 0, y: 0, width: 1000, height: 99 } }), false)
})

test('current active WXWork window is used directly for paste_only when the list only repeats the same root window', () => {
  const resolvePasteOnlyWxWorkWindow = (windowFinder as Record<string, unknown>).resolvePasteOnlyWxWorkWindow
  assert.equal(typeof resolvePasteOnlyWxWorkWindow, 'function')

  const result = (resolvePasteOnlyWxWorkWindow as Function)(
    { ...wxworkWindow, windowId: 'active', rootWindowId: 'active' },
    [{ ...wxworkWindow, windowId: 'active-child', rootWindowId: 'active', ownerWindowId: 'active', title: '' }],
  )

  assert.equal(result.ok, true)
  if (result.ok) {
    assert.equal(result.window.rootWindowId, 'active')
  }
})

test('non-WXWork active window refuses execution when multiple WXWork windows are visible', () => {
  const resolvePasteOnlyWxWorkWindow = (windowFinder as Record<string, unknown>).resolvePasteOnlyWxWorkWindow
  assert.equal(typeof resolvePasteOnlyWxWorkWindow, 'function')

  const result = (resolvePasteOnlyWxWorkWindow as Function)(
    { ...wxworkWindow, appType: 'chrome', title: 'Docs', processName: 'chrome.exe', executablePath: 'C:/Program Files/Google/Chrome/chrome.exe' },
    [
      { ...wxworkWindow, windowId: 'first', rootWindowId: 'first', processId: 111 },
      { ...wxworkWindow, windowId: 'exact', rootWindowId: 'exact' },
    ],
  )

  assert.equal(result.ok, false)
  if (!result.ok) {
    assert.equal(result.errorCode, 'TARGET_WINDOW_AMBIGUOUS')
  }
})

test('single valid WXWork window is selected for the pure keyboard paste_only path', () => {
  const candidates = windowFinder.collectVisibleWxWorkMainWindows([
    { ...wxworkWindow, executablePath: 'C:/Program Files/WXWork/WXWorkWeb.exe', processName: 'WXWorkWeb.exe', windowId: 'web' },
    { ...wxworkWindow, executablePath: '', processName: 'WXWork', windowId: 'main', rootWindowId: 'main' },
  ])

  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow(candidates)
  assert.equal(selection.ok, true)
  if (selection.ok) {
    assert.equal(selection.window.windowId, 'main')
  }
})

test('same WXWork process with multiple HWNDs is treated as ambiguous when no window is active', () => {
  const candidates = windowFinder.collectVisibleWxWorkMainWindows([
    { ...wxworkWindow, executablePath: '', processName: 'WXWork', windowId: 'main-1', rootWindowId: 'main-1', processId: 456 },
    { ...wxworkWindow, executablePath: 'D:/WXWork/WXWork.exe', processName: 'WXWork.exe', windowId: 'main-2', rootWindowId: 'main-2', processId: 456 },
  ])

  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow(candidates)
  assert.equal(selection.ok, false)
  if (!selection.ok) {
    assert.equal(selection.errorCode, 'TARGET_WINDOW_AMBIGUOUS')
  }
})

test('single main window plus WXWorkWeb background processes is not ambiguous', () => {
  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow([
    { ...wxworkWindow, windowId: 'main', rootWindowId: 'main' },
    { ...wxworkWindow, windowId: 'web-1', rootWindowId: 'web-1', processName: 'WXWorkWeb.exe', executablePath: 'C:/Program Files/WXWork/WXWorkWeb.exe', title: '' },
    { ...wxworkWindow, windowId: 'web-2', rootWindowId: 'web-2', processName: 'WXWorkWeb.exe', executablePath: 'C:/Program Files/WXWork/WXWorkWeb.exe', title: '' },
  ])

  assert.equal(selection.ok, true)
  if (selection.ok) {
    assert.equal(selection.window.windowId, 'main')
  }
})

test('same HWND returned by multiple providers is deduplicated to one candidate', () => {
  const inspected = windowFinder.inspectWxWorkWindowCandidates([
    { ...wxworkWindow, windowId: '1769682', rootWindowId: '1769682', source: 'node-window-manager' },
    { ...wxworkWindow, windowId: '1769682', rootWindowId: '1769682', source: 'active-win' },
  ])

  assert.equal(inspected.candidateCountBeforeFilter, 2)
  assert.equal(inspected.canonicalCandidateCount, 1)
  assert.equal(inspected.candidateCountAfterFilter, 1)
  assert.equal(inspected.rejectedCandidateCount, 0)
  assert.equal(inspected.selectedWindow?.hwnd, '1769682')
})

test('same rootHwnd duplicate wrapper is deduplicated and child helper is rejected', () => {
  const inspected = windowFinder.inspectWxWorkWindowCandidates([
    { ...wxworkWindow, windowId: '1769682', rootWindowId: '1769682', ownerWindowId: '0', source: 'node-window-manager' },
    { ...wxworkWindow, windowId: '1968272', rootWindowId: '1769682', ownerWindowId: '1769682', title: '', source: 'node-window-manager' },
  ])

  assert.equal(inspected.candidateCountBeforeFilter, 2)
  assert.equal(inspected.canonicalCandidateCount, 2)
  assert.equal(inspected.candidateCountAfterFilter, 1)
  assert.equal(inspected.rejectionReasons.some((item) => item.reason === 'empty_title'), true)
  assert.equal(inspected.selectedWindow?.hwnd, '1769682')
})

test('invisible untitled and owned popup windows are excluded', () => {
  const inspected = windowFinder.inspectWxWorkWindowCandidates([
    { ...wxworkWindow, windowId: 'main', rootWindowId: 'main' },
    { ...wxworkWindow, windowId: 'hidden', rootWindowId: 'hidden', title: '', isVisible: false },
    { ...wxworkWindow, windowId: 'owned', rootWindowId: 'owned', ownerWindowId: 'main', title: '企业微信' },
  ])

  assert.equal(inspected.candidateCountAfterFilter, 1)
  assert.equal(inspected.rejectionReasons.some((item) => item.reason === 'not_visible'), true)
  assert.equal(inspected.rejectionReasons.some((item) => item.reason === 'owned_window'), true)
})

test('enterprise wechat main window plus settings popup only keeps the main window', () => {
  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow([
    { ...wxworkWindow, windowId: 'main', rootWindowId: 'main' },
    { ...wxworkWindow, windowId: 'settings', rootWindowId: 'main', ownerWindowId: 'main', title: '设置' },
  ])

  assert.equal(selection.ok, true)
  if (selection.ok) {
    assert.equal(selection.window.windowId, 'main')
  }
})

test('enterprise wechat main window plus image preview window only keeps the main window', () => {
  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow([
    { ...wxworkWindow, windowId: 'main', rootWindowId: 'main' },
    { ...wxworkWindow, windowId: 'preview', rootWindowId: 'main', ownerWindowId: 'main', title: '图片预览' },
  ])

  assert.equal(selection.ok, true)
  if (selection.ok) {
    assert.equal(selection.window.windowId, 'main')
  }
})

test('two real enterprise wechat main windows remain ambiguous', () => {
  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow([
    { ...wxworkWindow, windowId: 'main-1', rootWindowId: 'main-1', processId: 101 },
    { ...wxworkWindow, windowId: 'main-2', rootWindowId: 'main-2', processId: 202 },
  ])

  assert.equal(selection.ok, false)
  if (!selection.ok) {
    assert.equal(selection.errorCode, 'TARGET_WINDOW_AMBIGUOUS')
  }
})

test('no main window returns TARGET_WINDOW_NOT_FOUND with diagnostics', () => {
  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow([
    { ...wxworkWindow, windowId: 'web', rootWindowId: 'web', processName: 'WXWorkWeb.exe', executablePath: 'C:/Program Files/WXWork/WXWorkWeb.exe', title: '' },
  ])

  assert.equal(selection.ok, false)
  if (!selection.ok) {
    assert.equal(selection.errorCode, 'TARGET_WINDOW_NOT_FOUND')
    assert.equal(selection.diagnostics.candidateCountBeforeFilter, 1)
  }
})

test('paste_only blocks when no valid WXWork main window is found', async () => {
  const input = new RecordingInputDriver()
  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p0',
    requestDigest: 'd0',
    conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
  }, {
    input,
    clipboard: new ClipboardController({ formats: ['text'], data: { text: 'old' } }),
    findTargetWindow: async () => ({ ok: false, errorCode: 'TARGET_WINDOW_NOT_FOUND', candidates: [] }),
    activateTargetWindow: async () => ({ ok: true }),
    sleep: async () => undefined,
  })

  assert.equal(result.status, 'blocked')
  assert.equal(result.errorCode, 'TARGET_WINDOW_NOT_FOUND')
  assert.equal(result.sendKeyCount, 0)
  assert.equal(result.messageSent, false)
  assert.deepEqual(input.events, [])
})

test('paste_only blocks on ambiguous windows without writing draft or attachments and exposes diagnostics', async () => {
  const input = new RecordingInputDriver()
  const attachmentRoot = path.join(os.tmpdir(), 'broadcast-runtime-ambiguous-window', 'runtime', 'broadcast_attachments')
  const baseDir = path.join(attachmentRoot, 'bot-1', '1', 'g1')
  await fs.mkdir(baseDir, { recursive: true })
  const attachmentPath = path.join(baseDir, 'asset-1_quote.pdf')
  await fs.writeFile(attachmentPath, Buffer.from('pdf-data', 'utf8'))

  try {
    const result = await runPasteOnlyTask({
      action: 'paste_draft',
      idempotencyKey: 'ambiguous-1',
      requestDigest: 'ambiguous-digest',
      conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
      attachmentRoot,
      attachments: [{
        relativePath: path.join('bot-1', '1', 'g1', 'asset-1_quote.pdf'),
        filename: 'quote.pdf',
        size: (await fs.stat(attachmentPath)).size,
        sha256: sha256('pdf-data'),
      }],
    }, {
      input,
      clipboard: new ClipboardController({ formats: ['text'], data: { text: 'old' } }),
      findTargetWindow: async () => ({
        ok: false,
        errorCode: 'TARGET_WINDOW_AMBIGUOUS',
        candidates: [],
        diagnostics: {
          candidateCountBeforeFilter: 2,
          canonicalCandidateCount: 2,
          candidateCountAfterFilter: 2,
          rejectedCandidateCount: 0,
          selectedWindow: null,
          candidates: [
            { hwnd: '1769682', rootHwnd: '1769682', ownerHwnd: '0', processId: 5516, processName: 'wxwork.exe', executableName: 'wxwork.exe', title: '??????', className: 'Qt', visible: true, minimized: false, source: 'node-window-manager', accepted: true, rejectionReason: null },
          ],
          rejectionReasons: [],
        },
      }),
      activateTargetWindow: async () => ({ ok: true }),
      sleep: async () => undefined,
    })

    assert.equal(result.status, 'blocked')
    assert.equal(result.errorCode, 'TARGET_WINDOW_AMBIGUOUS')
    assert.equal(result.draftWritten, false)
    assert.equal(result.inputLocated, false)
    assert.equal(result.attachmentPasteRequested, false)
    assert.equal(result.sendKeyCount, 0)
    assert.equal(result.messageSent, false)
    assert.equal(result.candidateCountBeforeFilter, 2)
    assert.equal(result.canonicalCandidateCount, 2)
    assert.equal(Array.isArray(result.rejectionReasons), true)
    assert.deepEqual(input.events, [])
  } finally {
    await fs.rm(path.join(os.tmpdir(), 'broadcast-runtime-ambiguous-window'), { recursive: true, force: true })
  }
})

test('paste_only follows the search-to-input state machine and does not send the draft', async () => {
  const input = new RecordingInputDriver()
  const sleeps: number[] = []
  const clipboardWrites: string[] = []
  const clipboard = new ClipboardController(undefined, {
    ...fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }),
    writeText(text: string) {
      clipboardWrites.push(text)
    },
    readText() {
      return clipboardWrites.at(-1) ?? 'old clipboard'
    },
  })

  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p1',
    requestDigest: 'd1',
    conversationName: 'Customer A',
    draftText: 'First line\nSecond line',
  }, {
    input,
    clipboard,
    fileClipboard: new RecordingFileClipboardController() as never,
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    getActiveWindow: async () => wxworkWindow,
    sleep: async (ms) => { sleeps.push(ms) },
  })

  assert.equal(result.status, 'succeeded')
  assert.equal(result.stage, 'text_pasted_unverified')
  assert.equal(result.terminal_confirmed, true)
  assert.equal(result.enter_dispatched, false)
  assert.equal(result.message_sent, false)
  assert.equal(result.result_text, '已粘贴，未发送')
  assert.equal(result.contentVerified, false)
  assert.equal(result.verificationFailed, false)
  assert.equal(result.observationAvailable, false)
  assert.equal(result.actualTextLength, null)
  assert.equal(result.actualCodePointCount, null)
  assert.equal(result.actualDigest, null)
  assert.equal(result.actualLineCount, null)
  assert.deepEqual(clipboardWrites, ['Customer A', 'First line\nSecond line'])
  assert.equal(sleeps.length, 4)
  assert.deepEqual(sleeps, [300, 200, 800, 800])
  assert.deepEqual(input.events, [
    { type: 'hotkey', payload: ['Control', 'F'] },
    { type: 'hotkey', payload: ['Control', 'A'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
    { type: 'hotkey', payload: ['Enter'] },
    { type: 'hotkey', payload: ['Control', 'A'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
  ])
  assert.equal(result.searchShortcutCount, 1)
  assert.equal(result.conversationInputCount, 1)
  assert.equal(result.conversationPasteCount, 1)
  assert.equal(result.conversationConfirmEnterCount, 1)
  assert.equal(result.draftPasteCount, 1)
  assert.equal(result.sendKeyCount, 0)
  assert.equal(result.messageSent, false)
  assert.equal(result.draftWritten, true)
  assert.deepEqual(
    (result.evidence as Array<Record<string, unknown>>).map((item) => item.phase),
    [
      'wechat_activated',
      'search_focused',
      'search_cleared',
      'conversation_name_pasted',
      'conversation_search_waiting',
      'conversation_enter_sent',
      'conversation_input_waiting',
      'conversation_input_cleared',
      'message_pasted',
      'prepare',
    ],
  )
  assert.equal(clipboard.currentText(), 'old clipboard')
  assert.equal(result.conversationName, undefined)
  assert.equal(result.draftText, undefined)
})

test('managed window activation uses SightFlow-style method order and confirms WXWork focus', async () => {
  const activateManagedWindow = (windowActivator as Record<string, unknown>).activateManagedWindow
  assert.equal(typeof activateManagedWindow, 'function')

  const calls: string[] = []
  let activeCheckCount = 0
  const nativeWindow = {
    isWindow() { return true },
    isVisible() { return true },
    restore(this: Record<string, unknown>) {
      assert.equal(this, nativeWindow)
      calls.push('restore')
    },
    show(this: Record<string, unknown>) {
      assert.equal(this, nativeWindow)
      calls.push('show')
    },
    showWindow(this: Record<string, unknown>) {
      assert.equal(this, nativeWindow)
      calls.push('showWindow')
      throw new Error('showWindow failed')
    },
    focus(this: Record<string, unknown>) {
      assert.equal(this, nativeWindow)
      calls.push('focus')
    },
    setForeground(this: Record<string, unknown>) {
      assert.equal(this, nativeWindow)
      calls.push('setForeground')
    },
    activate(this: Record<string, unknown>) {
      assert.equal(this, nativeWindow)
      calls.push('activate')
    },
    bringToTop(this: Record<string, unknown>) {
      assert.equal(this, nativeWindow)
      calls.push('bringToTop')
    },
  }

  const result = await (activateManagedWindow as Function)(nativeWindow, wxworkWindow, {
    sleep: async () => undefined,
    getActiveWindowDescriptor: async () => {
      activeCheckCount += 1
      if (activeCheckCount === 1) {
        return {
          ...wxworkWindow,
          appType: 'chrome',
          title: 'Docs',
          processName: 'chrome.exe',
          executablePath: 'C:/Program Files/Google/Chrome/chrome.exe',
        }
      }
      return { ...wxworkWindow }
    },
  })

  assert.equal(result.ok, true)
  assert.deepEqual(calls, ['restore', 'show', 'showWindow', 'focus', 'setForeground', 'activate', 'bringToTop'])
})

test('managed window activation succeeds immediately when active window is already WXWork', async () => {
  const activateManagedWindow = (windowActivator as Record<string, unknown>).activateManagedWindow
  assert.equal(typeof activateManagedWindow, 'function')

  const calls: string[] = []
  const result = await (activateManagedWindow as Function)({
    isWindow() { return true },
    isVisible() { return true },
    restore() { calls.push('restore') },
    show() { calls.push('show') },
    showWindow() { calls.push('showWindow') },
    focus() { calls.push('focus') },
    setForeground() { calls.push('setForeground') },
    activate() { calls.push('activate') },
    bringToTop() { calls.push('bringToTop') },
  }, wxworkWindow, {
    sleep: async () => undefined,
    getActiveWindowDescriptor: async () => ({ ...wxworkWindow }),
  })

  assert.equal(result.ok, true)
  assert.deepEqual(calls, [])
})

test('managed window activation does not succeed when polling reaches a different WXWork HWND', async () => {
  const activateManagedWindow = (windowActivator as Record<string, unknown>).activateManagedWindow
  assert.equal(typeof activateManagedWindow, 'function')

  let pollCount = 0
  const result = await (activateManagedWindow as Function)({
    isWindow() { return true },
    isVisible() { return true },
  }, { ...wxworkWindow, windowId: 'target-a', title: 'Customer A' }, {
    sleep: async () => undefined,
    getActiveWindowDescriptor: async () => {
      pollCount += 1
      if (pollCount === 1) return null
      return {
        ...wxworkWindow,
        windowId: 'target-b',
        title: 'Customer B',
        clientBounds: { x: 0, y: 0, width: 0, height: 0 },
        boundsLogical: { x: 0, y: 0, width: 0, height: 0 },
        isVisible: true,
      }
    },
  })

  assert.equal(result.ok, false)
  if (!result.ok) {
    assert.equal(result.errorCode, 'WINDOW_ACTIVATION_FAILED')
  }
})

test('managed window activation returns WINDOW_ACTIVATION_FAILED only after all polls miss WXWork', async () => {
  const activateManagedWindow = (windowActivator as Record<string, unknown>).activateManagedWindow
  assert.equal(typeof activateManagedWindow, 'function')

  let pollCount = 0
  const result = await (activateManagedWindow as Function)({
    isWindow() { return true },
    isVisible() { return true },
  }, wxworkWindow, {
    sleep: async () => undefined,
    getActiveWindowDescriptor: async () => {
      pollCount += 1
      return { ...wxworkWindow, appType: 'chrome', title: 'Docs', processName: 'chrome.exe', executablePath: 'C:/Program Files/Google/Chrome/chrome.exe' }
    },
  })

  assert.equal(result.ok, false)
  assert.equal(pollCount, 7)
  if (!result.ok) {
    assert.equal(result.errorCode, 'WINDOW_ACTIVATION_FAILED')
  }
})

test('managed window activation logs structured safe fields without sensitive content', async () => {
  const activateManagedWindow = (windowActivator as Record<string, unknown>).activateManagedWindow
  assert.equal(typeof activateManagedWindow, 'function')

  const logs: string[] = []
  const originalInfo = console.info
  console.info = (...args: unknown[]) => {
    logs.push(args.map((arg) => String(arg)).join(' '))
  }

  try {
    let activeCheckCount = 0
    await (activateManagedWindow as Function)({
      isWindow() { return true },
      isVisible() { return true },
      restore() {},
    }, {
      ...wxworkWindow,
      title: 'Sensitive Conversation Name',
      processName: 'WXWork.exe',
    }, {
      sleep: async () => undefined,
      getActiveWindowDescriptor: async () => {
        activeCheckCount += 1
        if (activeCheckCount === 1) {
          return {
            ...wxworkWindow,
            appType: 'chrome',
            title: 'draftText token clipboard body',
            processName: 'chrome.exe',
            executablePath: 'C:/Program Files/Google/Chrome/chrome.exe',
          }
        }
        return {
          ...wxworkWindow,
          windowId: 'focused-window',
          title: 'draftText token clipboard body',
        }
      },
    })
  } finally {
    console.info = originalInfo
  }

  assert.equal(logs.some((line) => line.includes('event=window_activation_target')), true)
  assert.equal(logs.some((line) => line.includes('event=window_activation_method')), true)
  assert.equal(logs.some((line) => line.includes('event=window_activation_poll')), true)
  assert.equal(logs.some((line) => line.includes('Sensitive Conversation Name')), false)
  assert.equal(logs.some((line) => line.includes('draftText')), false)
  assert.equal(logs.some((line) => line.includes('token')), false)
  assert.equal(logs.some((line) => line.includes('clipboard body')), false)
})

test('paste_only returns warning when successful paste cannot restore clipboard', async () => {
  class FailingClipboard extends ClipboardController {
    async restore(): Promise<void> { throw new Error('restore failed') }
  }

  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p2',
    requestDigest: 'd2',
    conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
  }, {
    input: new RecordingInputDriver(),
    clipboard: new FailingClipboard({ formats: ['text'], data: { text: 'old' } }),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
  })

  assert.equal(result.status, 'succeeded_with_warning')
  assert.equal(result.errorCode, 'CLIPBOARD_RESTORE_MISMATCH')
  assert.equal(result.clipboardRestoreFailed, true)
  assert.equal(result.messageSent, false)
})

test('paste_only preserves original failure when restore also fails', async () => {
  class FailingClipboard extends ClipboardController {
    async restore(): Promise<void> { throw new Error('restore failed') }
  }

  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p3',
    requestDigest: 'd3',
    conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
  }, {
    input: new RecordingInputDriver(),
    clipboard: new FailingClipboard({ formats: ['text'], data: { text: 'old' } }),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => { throw new Error('WINDOW_ACTIVATION_FAILED') },
    sleep: async () => undefined,
  })

  assert.equal(result.status, 'failed')
  assert.equal(result.errorCode, 'WINDOW_ACTIVATION_FAILED')
  assert.equal(result.clipboardRestoreFailed, true)
})

test('paste_only only returns succeeded after explicit content verification passes', async () => {
  const input = new RecordingInputDriver()
  const clipboard = new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }))

  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p4',
    requestDigest: 'd4',
    conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
  }, {
    input,
    clipboard,
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
  } as never)

  assert.equal(result.status, 'succeeded')
  assert.equal(result.stage, 'text_pasted_unverified')
  assert.equal(result.inputLocated, false)
  assert.equal(result.draftWritten, true)
  assert.equal(result.contentVerified, false)
  assert.equal(result.verificationFailed, false)
  assert.deepEqual(input.events, [
    { type: 'hotkey', payload: ['Control', 'F'] },
    { type: 'hotkey', payload: ['Control', 'A'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
    { type: 'hotkey', payload: ['Enter'] },
    { type: 'hotkey', payload: ['Control', 'A'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
  ])
})

test('runtime host generates UUID-like task ids instead of process-local counters', async () => {
  const hostA = new RuntimeHost({
    input: new RecordingInputDriver(),
    clipboard: new ClipboardController({ formats: ['text'], data: { text: 'old' } }),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
      })
  const hostB = new RuntimeHost({
    input: new RecordingInputDriver(),
    clipboard: new ClipboardController({ formats: ['text'], data: { text: 'old' } }),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
      })

  const request = {
    action: 'paste_draft' as const,
    idempotencyKey: 'idem-uuid-1',
    requestDigest: 'digest-uuid-1',
    conversationName: 'Customer A',
    draftText: 'First line\nSecond line',
  }

  const first = await hostA.createTask(request)
  const second = await hostB.createTask({ ...request, idempotencyKey: 'idem-uuid-2', requestDigest: 'digest-uuid-2' })

  assert.match(first.id, /^task-[0-9a-f-]{36}$/i)
  assert.match(second.id, /^task-[0-9a-f-]{36}$/i)
  assert.notEqual(first.id, 'task-1')
  assert.notEqual(second.id, 'task-1')
  assert.notEqual(first.id, second.id)
})

test('runtime host reuses idempotency key and does not repeat paste task', async () => {
  const input = new RecordingInputDriver()
  const host = new RuntimeHost({
    input,
    clipboard: new ClipboardController({ formats: ['text'], data: { text: 'old' } }),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    getActiveWindow: async () => wxworkWindow,
    sleep: async () => undefined,
  })
  const request = {
    action: 'paste_draft' as const,
    idempotencyKey: 'idem-1',
    requestDigest: 'digest-1',
    conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
  }
  const first = await host.createTask(request)
  const second = await host.createTask({ ...request, draftText: 'changed' })
  assert.equal(first.id, second.id)
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (host.getTask(first.id)?.status === 'succeeded') {
      break
    }
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
  assert.equal(host.getTask(first.id)?.status, 'succeeded')
  assert.equal(input.events.filter((event) => event.type === 'hotkey').length, 6)
})

test('paste-draft tasks share one execution lane and run in FIFO order', async () => {
  const started: string[] = []
  const finished: string[] = []
  const releases = new Map<string, () => void>()
  const host = new RuntimeHost()
  host.runner.run = (async (request: { idempotencyKey: string }) => {
    started.push(request.idempotencyKey)
    await new Promise<void>((resolve) => { releases.set(request.idempotencyKey, resolve) })
    finished.push(request.idempotencyKey)
    return { status: 'succeeded', stage: `done-${request.idempotencyKey}` }
  }) as never

  const first = await host.createTask({
    action: 'paste_draft',
    idempotencyKey: 'fifo-1',
    requestDigest: 'digest-fifo-1',
    conversationName: 'Customer A',
    draftText: 'hello',
  })
  const second = await host.createTask({
    action: 'paste_draft',
    idempotencyKey: 'fifo-2',
    requestDigest: 'digest-fifo-2',
    conversationName: 'Customer A',
    draftText: 'hello',
  })

  assert.equal(first.status, 'running')
  assert.equal(first.executionLaneKey, 'wxwork-main-window')
  assert.equal(second.status, 'queued')
  assert.equal(second.stage, 'queued_for_execution_lane')
  assert.equal(second.executionLaneKey, 'wxwork-main-window')
  assert.deepEqual(started, ['fifo-1'])
  releases.get('fifo-1')?.()
  await new Promise((resolve) => setTimeout(resolve, 20))
  assert.deepEqual(finished, ['fifo-1'])
  assert.deepEqual(started, ['fifo-1', 'fifo-2'])

  releases.get('fifo-2')?.()
  await new Promise((resolve) => setTimeout(resolve, 20))
  assert.equal(host.getTask(second.id)?.status, 'succeeded')
})

test('queued tasks can be cancelled before they start and never execute', async () => {
  const started: string[] = []
  const controls: { releaseFirst?: () => void } = {}
  const host = new RuntimeHost()
  host.runner.run = (async (request: { idempotencyKey: string }) => {
    started.push(request.idempotencyKey)
    if (request.idempotencyKey === 'cancel-first') {
      await new Promise<void>((resolve) => { controls.releaseFirst = () => resolve() })
    }
    return { status: 'succeeded', stage: `done-${request.idempotencyKey}` }
  }) as never

  await host.createTask({
    action: 'paste_draft',
    idempotencyKey: 'cancel-first',
    requestDigest: 'digest-cancel-first',
    conversationName: 'Customer A',
    draftText: 'hello',
  })
  const queued = await host.createTask({
    action: 'paste_draft',
    idempotencyKey: 'cancel-second',
    requestDigest: 'digest-cancel-second',
    conversationName: 'Customer A',
    draftText: 'hello',
  })

  const cancelled = host.cancelTask(queued.id)
  assert.equal(cancelled?.status, 'cancelled')
  controls.releaseFirst?.()
  await new Promise((resolve) => setTimeout(resolve, 20))
  assert.deepEqual(started, ['cancel-first'])
  assert.equal(host.getTask(queued.id)?.status, 'cancelled')
})

test('runtime host rejects new task creation once shutdown begins and leaves no registry residue', async () => {
  const controls: { releaseRunning?: () => void } = {}
  const started: string[] = []
  const host = new RuntimeHost()
  host.runner.run = (async (request: { idempotencyKey: string }) => {
    started.push(request.idempotencyKey)
    await new Promise<void>((resolve) => { controls.releaseRunning = () => resolve() })
    return { status: 'succeeded', stage: 'completed' }
  }) as never

  const running = await host.createTask({
    action: 'paste_draft',
    idempotencyKey: 'shutdown-running',
    requestDigest: 'shutdown-running-digest',
    conversationName: 'Customer A',
    draftText: 'hello',
  })
  const queued = await host.createTask({
    action: 'paste_draft',
    idempotencyKey: 'shutdown-queued',
    requestDigest: 'shutdown-queued-digest',
    conversationName: 'Customer A',
    draftText: 'hello',
  })

  const shutdownPromise = host.shutdown()

  await assert.rejects(
    () => host.createTask({
      action: 'paste_draft',
      idempotencyKey: 'shutdown-rejected',
      requestDigest: 'shutdown-rejected-digest',
      conversationName: 'Customer A',
      draftText: 'hello',
    }),
    (error: unknown) => {
      assert.equal((error as { errorCode?: string }).errorCode, 'RUNTIME_SHUTTING_DOWN')
      assert.equal((error as { statusCode?: number }).statusCode, 503)
      return true
    },
  )

  assert.equal(host.isShuttingDown(), true)
  assert.equal(host.getTask(queued.id)?.status, 'interrupted')
  assert.equal(host.getTask(queued.id)?.stage, 'runtime_shutdown')
  assert.equal(host.activeTaskCount(), 1)
  assert.deepEqual(started, ['shutdown-running'])
  assert.equal(host.registry.all().some((task) => task.idempotencyKey === 'shutdown-rejected'), false)

  controls.releaseRunning?.()
  await shutdownPromise
  assert.equal(host.getTask(running.id)?.status, 'cancelled')
  assert.equal(host.getTask(running.id)?.stage, 'cancelled')
})

test('paste_only appends attachments after verified text and never presses Enter', async () => {
  const input = new RecordingInputDriver()
  const clipboard = new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }))
  const fileClipboard = new RecordingFileClipboardController()
  const attachmentRoot = path.join(
    os.tmpdir(),
    'broadcast-runtime-test',
    'runtime',
    'broadcast_attachments',
  )
  const baseDir = path.join(
    attachmentRoot,
    'bot-1',
    '1',
    'g1',
  )
  await fs.mkdir(baseDir, { recursive: true })
  const attachmentPathA = path.join(baseDir, 'asset-1_quote.pdf')
  const attachmentPathB = path.join(baseDir, 'asset-2_screenshot.png')
  await fs.writeFile(attachmentPathA, Buffer.from('pdf-data', 'utf8'))
  await fs.writeFile(attachmentPathB, Buffer.from('png-data-123', 'utf8'))

  const attachments: RuntimeAttachmentPayload[] = [
    {
      relativePath: path.join('bot-1', '1', 'g1', 'asset-1_quote.pdf'),
      filename: 'quote.pdf',
      size: (await fs.stat(attachmentPathA)).size,
      sha256: sha256('pdf-data'),
    },
    {
      relativePath: path.join('bot-1', '1', 'g1', 'asset-2_screenshot.png'),
      filename: 'screenshot.png',
      size: (await fs.stat(attachmentPathB)).size,
      sha256: sha256('png-data-123'),
    },
  ]

  try {
    const result = await runPasteOnlyTask({
      action: 'paste_draft',
      idempotencyKey: 'paste-attachments',
      requestDigest: 'digest-attachments',
      conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
      attachmentRoot,
      attachments,
    }, {
      input,
      clipboard,
      fileClipboard: fileClipboard as never,
      findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      sleep: async () => undefined,
      getActiveWindow: async () => wxworkWindow,
    } as never)

    assert.equal(result.status, 'succeeded_with_warning')
    assert.equal(result.stage, 'attachments_pasted_unverified')
    assert.equal(result.messageSent, false)
    assert.equal(result.contentVerified, false)
    assert.equal(result.attachmentsPrepared, true)
    assert.equal(result.attachmentPasteRequested, true)
    assert.equal(result.attachmentsVerified, false)
    assert.equal(result.attachmentCount, 2)
    assert.deepEqual(input.events, [
      { type: 'hotkey', payload: ['Control', 'F'] },
      { type: 'hotkey', payload: ['Control', 'A'] },
      { type: 'hotkey', payload: ['Control', 'V'] },
      { type: 'hotkey', payload: ['Enter'] },
      { type: 'hotkey', payload: ['Control', 'A'] },
      { type: 'hotkey', payload: ['Control', 'V'] },
      { type: 'hotkey', payload: ['Control', 'V'] },
    ])
    assert.equal(fileClipboard.writes.length, 1)
    assert.deepEqual(
      fileClipboard.writes[0].map(({ resolvedPath, ...item }) => item),
      attachments,
    )
    assert.equal(typeof fileClipboard.writes[0][0]?.resolvedPath, 'string')
    assert.equal(typeof fileClipboard.writes[0][1]?.resolvedPath, 'string')
  } finally {
    await fs.rm(path.join(os.tmpdir(), 'broadcast-runtime-test'), { recursive: true, force: true })
  }
})


test('paste_only blocks attachment paste when file digest mismatches', async () => {
  const input = new RecordingInputDriver()
  const clipboard = new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }))
  const fileClipboard = new RecordingFileClipboardController()
  const attachmentRoot = path.join(
    os.tmpdir(),
    'broadcast-runtime-test-mismatch',
    'runtime',
    'broadcast_attachments',
  )
  const baseDir = path.join(
    attachmentRoot,
    'bot-1',
    '1',
    'g1',
  )
  await fs.mkdir(baseDir, { recursive: true })
  const attachmentPath = path.join(baseDir, 'asset-1_test.txt')
  await fs.writeFile(attachmentPath, Buffer.from('real-data', 'utf8'))

  try {
    const result = await runPasteOnlyTask({
      action: 'paste_draft',
      idempotencyKey: 'paste-attachments-mismatch',
      requestDigest: 'digest-attachments-mismatch',
      conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
      attachmentRoot,
      attachments: [
        {
          relativePath: path.join('bot-1', '1', 'g1', 'asset-1_test.txt'),
          filename: 'test.txt',
          size: (await fs.stat(attachmentPath)).size,
          sha256: sha256('different-data'),
        },
      ],
    }, {
      input,
      clipboard,
      fileClipboard: fileClipboard as never,
      findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      sleep: async () => undefined,
    } as never)

    assert.equal(result.status, 'failed')
    assert.equal(result.errorCode, 'ATTACHMENT_HASH_MISMATCH')
    assert.equal(result.attachmentPasteRequested, false)
    assert.deepEqual(input.events, [])
    assert.deepEqual(fileClipboard.writes, [])
  } finally {
    await fs.rm(path.join(os.tmpdir(), 'broadcast-runtime-test-mismatch'), { recursive: true, force: true })
  }
})

test('file clipboard helper encodes PowerShell command as UTF-16LE base64', () => {
  const script = 'Write-Output "中文 (test)"'
  const encoded = encodePowerShellCommandUtf16Le(script)
  assert.equal(Buffer.from(encoded, 'base64').toString('utf16le'), script)
})

test('file clipboard helper payload uses resolved paths and UTF-8 JSON', () => {
  const payload = buildFileClipboardHelperPayload([
    {
      relativePath: 'bot-1/1/g1/截图 (1).png',
      filename: '截图 (1).png',
      size: 1,
      sha256: 'abc',
      resolvedPath: 'C:\\runtime\\广播\\截图 (1).png',
    },
    {
      relativePath: 'bot-1/1/g1/报表.xlsx',
      filename: '报表.xlsx',
      size: 2,
      sha256: 'def',
      resolvedPath: 'C:\\runtime\\广播\\报表.xlsx',
    },
  ])
  assert.deepEqual(payload, {
    files: ['C:\\runtime\\广播\\截图 (1).png', 'C:\\runtime\\广播\\报表.xlsx'],
    expectedCount: 2,
  })
})

test('file clipboard helper args include hidden STA PowerShell options and no paths in command line', () => {
  const args = buildFileClipboardHelperArgs('Write-Output ok')
  assert.equal(args.includes('-STA'), true)
  assert.equal(args.includes('-NonInteractive'), true)
  assert.equal(args.includes('-WindowStyle'), true)
  assert.equal(args.includes('Hidden'), true)
  assert.equal(args.some((item) => item.includes('C:\\')), false)
})

test('file clipboard helper parses successful CF_HDROP output', () => {
  const parsed = parseFileClipboardHelperOutput(
    '{"ok":true,"clipboardFormat":"CF_HDROP","expectedCount":2,"observedCount":2,"pathsMatched":true}',
    2,
  )
  assert.deepEqual(parsed, {
    ok: true,
    clipboardFormat: 'CF_HDROP',
    expectedCount: 2,
    observedCount: 2,
    pathsMatched: true,
  })
})

test('file clipboard helper rejects empty/non-JSON/noisy output and path/count mismatches', () => {
  assert.throws(() => parseFileClipboardHelperOutput('', 1), /FILE_CLIPBOARD_OUTPUT_INVALID/)
  assert.throws(() => parseFileClipboardHelperOutput('not-json', 1), /FILE_CLIPBOARD_OUTPUT_INVALID/)
  assert.throws(() => parseFileClipboardHelperOutput('x\n{"ok":true,"clipboardFormat":"CF_HDROP","expectedCount":1,"observedCount":1,"pathsMatched":true}', 1), /FILE_CLIPBOARD_OUTPUT_INVALID/)
  assert.throws(() => parseFileClipboardHelperOutput('{"ok":true,"clipboardFormat":"TEXT","expectedCount":1,"observedCount":1,"pathsMatched":true}', 1), /FILE_CLIPBOARD_OUTPUT_INVALID/)
  assert.throws(() => parseFileClipboardHelperOutput('{"ok":true,"clipboardFormat":"CF_HDROP","expectedCount":9,"observedCount":1,"pathsMatched":true}', 1), /FILE_CLIPBOARD_COUNT_MISMATCH/)
  assert.throws(() => parseFileClipboardHelperOutput('{"ok":true,"clipboardFormat":"CF_HDROP","expectedCount":1,"observedCount":1,"pathsMatched":false}', 1), /FILE_CLIPBOARD_PATH_MISMATCH/)
})

test('WindowsFileClipboardController spawns hidden PowerShell and sends UTF-8 stdin JSON only', async () => {
  const child = new FakeChildProcess()
  let capturedCommand = ''
  let capturedArgs: string[] = []
  let capturedOptions: unknown
  const controller = new WindowsFileClipboardController(((command: string, args: string[], options: unknown) => {
    capturedCommand = command
    capturedArgs = args
    capturedOptions = options
    queueMicrotask(() => {
      child.stdout.emit('data', Buffer.from('{"ok":true,"clipboardFormat":"CF_HDROP","expectedCount":2,"observedCount":2,"pathsMatched":true}', 'utf8'))
      child.emit('close', 0)
    })
    return child as unknown as never
  }) as never)

  const result = await controller.writeFiles([
    {
      relativePath: 'a/中文 文件.png',
      filename: '中文 文件.png',
      size: 1,
      sha256: 'abc',
      resolvedPath: 'C:\\safe root\\中文 文件.png',
    },
    {
      relativePath: 'a/report (1).xlsx',
      filename: 'report (1).xlsx',
      size: 2,
      sha256: 'def',
      resolvedPath: 'C:\\safe root\\report (1).xlsx',
    },
  ])

  assert.equal(capturedCommand, 'powershell.exe')
  assert.deepEqual(capturedOptions, {
    shell: false,
    windowsHide: true,
    stdio: ['pipe', 'pipe', 'pipe'],
  })
  assert.equal(capturedArgs.includes('-STA'), true)
  assert.equal(capturedArgs.includes('-NonInteractive'), true)
  assert.equal(capturedArgs.some((item) => item.includes('中文 文件.png')), false)
  assert.equal(capturedArgs.some((item) => item.includes('report (1).xlsx')), false)
  assert.equal(child.stdinEnded, true)
  assert.deepEqual(JSON.parse(Buffer.concat(child.stdinWrites).toString('utf8')), {
    files: ['C:\\safe root\\中文 文件.png', 'C:\\safe root\\report (1).xlsx'],
    expectedCount: 2,
  })
  assert.equal(result.expectedCount, 2)
})

test('WindowsFileClipboardController fails on helper non-zero exit and spawn ENOENT', async () => {
  const failingChild = new FakeChildProcess()
  const controller = new WindowsFileClipboardController((() => {
    queueMicrotask(() => {
      failingChild.stdout.emit('data', Buffer.from('{"ok":false,"errorCode":"FILE_CLIPBOARD_HELPER_FAILED","sanitizedMessage":"Unable to prepare the file clipboard"}', 'utf8'))
      failingChild.emit('close', 1)
    })
    return failingChild as unknown as never
  }) as never)
  await assert.rejects(
    () => controller.writeFiles([{ relativePath: 'a', filename: 'a', size: 1, sha256: 'x', resolvedPath: 'C:\\a.txt' }]),
    /FILE_CLIPBOARD_HELPER_FAILED/,
  )

  const missing = new WindowsFileClipboardController((() => {
    const error = new Error('spawn failed') as Error & { code?: string }
    error.code = 'ENOENT'
    throw error
  }) as never)
  await assert.rejects(
    () => missing.writeFiles([{ relativePath: 'a', filename: 'a', size: 1, sha256: 'x', resolvedPath: 'C:\\a.txt' }]),
    /FILE_CLIPBOARD_HELPER_SPAWN_FAILED/,
  )
})

test('post-paste delay obeys lower and upper bounds', () => {
  assert.equal(computeAttachmentPostPasteDelayMs(0), 1000)
  assert.equal(computeAttachmentPostPasteDelayMs(10 * 1024 * 1024), 1300)
  assert.equal(computeAttachmentPostPasteDelayMs(200 * 1024 * 1024), 3000)
})

test('paste_only fails before attachment Ctrl+V when target window loses foreground after helper success', async () => {
  const input = new RecordingInputDriver()
  const clipboard = new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }))
  const fileClipboard = new RecordingFileClipboardController()
  const attachmentRoot = path.join(os.tmpdir(), 'broadcast-runtime-target-lost', 'runtime', 'broadcast_attachments')
  const baseDir = path.join(attachmentRoot, 'bot-1', '1', 'g1')
  await fs.mkdir(baseDir, { recursive: true })
  const attachmentPath = path.join(baseDir, 'asset-1_quote.pdf')
  await fs.writeFile(attachmentPath, Buffer.from('pdf-data', 'utf8'))

  let activeWindowCheckCount = 0
  try {
    const result = await runPasteOnlyTask({
      action: 'paste_draft',
      idempotencyKey: 'lost-target',
      requestDigest: 'lost-target-digest',
      conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
      attachmentRoot,
      attachments: [{
        relativePath: path.join('bot-1', '1', 'g1', 'asset-1_quote.pdf'),
        filename: 'quote.pdf',
        size: (await fs.stat(attachmentPath)).size,
        sha256: sha256('pdf-data'),
      }],
    }, {
      input,
      clipboard,
      fileClipboard: fileClipboard as never,
      findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      getActiveWindow: async () => {
        activeWindowCheckCount += 1
        return activeWindowCheckCount <= 4
          ? wxworkWindow
          : { ...wxworkWindow, windowId: 'chrome', rootWindowId: 'chrome', processName: 'chrome.exe', executablePath: 'C:/chrome.exe', appType: 'chrome' }
      },
      sleep: async () => undefined,
    } as never)

    assert.equal(result.status, 'failed')
    assert.equal(result.errorCode, 'TARGET_WINDOW_LOST_BEFORE_ATTACHMENT_PASTE')
    assert.equal(result.attachmentsPrepared, true)
    assert.equal(result.attachmentPasteRequested, false)
    assert.deepEqual(input.events, [
      { type: 'hotkey', payload: ['Control', 'F'] },
      { type: 'hotkey', payload: ['Control', 'A'] },
      { type: 'hotkey', payload: ['Control', 'V'] },
      { type: 'hotkey', payload: ['Enter'] },
      { type: 'hotkey', payload: ['Control', 'A'] },
      { type: 'hotkey', payload: ['Control', 'V'] },
    ])
  } finally {
    await fs.rm(path.join(os.tmpdir(), 'broadcast-runtime-target-lost'), { recursive: true, force: true })
  }
})

test('paste_only maps reactivation failure before attachment paste to target-window-lost error', async () => {
  const input = new RecordingInputDriver()
  const clipboard = new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }))
  const fileClipboard = new RecordingFileClipboardController()
  const attachmentRoot = path.join(os.tmpdir(), 'broadcast-runtime-reactivation-failed', 'runtime', 'broadcast_attachments')
  const baseDir = path.join(attachmentRoot, 'bot-1', '1', 'g1')
  await fs.mkdir(baseDir, { recursive: true })
  const attachmentPath = path.join(baseDir, 'asset-1_quote.pdf')
  await fs.writeFile(attachmentPath, Buffer.from('pdf-data', 'utf8'))

  let activationCount = 0
  try {
    const result = await runPasteOnlyTask({
      action: 'paste_draft',
      idempotencyKey: 'reactivation-failed',
      requestDigest: 'reactivation-failed-digest',
      conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
      attachmentRoot,
      attachments: [{
        relativePath: path.join('bot-1', '1', 'g1', 'asset-1_quote.pdf'),
        filename: 'quote.pdf',
        size: (await fs.stat(attachmentPath)).size,
        sha256: sha256('pdf-data'),
      }],
    }, {
      input,
      clipboard,
      fileClipboard: fileClipboard as never,
      findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      activateTargetWindow: async () => {
        activationCount += 1
        return activationCount === 1
          ? { ok: true, window: wxworkWindow }
          : { ok: false, errorCode: 'WINDOW_ACTIVATION_FAILED' }
      },
      getActiveWindow: async () => wxworkWindow,
      sleep: async () => undefined,
    } as never)

    assert.equal(result.status, 'failed')
    assert.equal(result.errorCode, 'TARGET_WINDOW_LOST_BEFORE_ATTACHMENT_PASTE')
    assert.equal(result.attachmentsPrepared, true)
    assert.equal(result.attachmentPasteRequested, false)
  } finally {
    await fs.rm(path.join(os.tmpdir(), 'broadcast-runtime-reactivation-failed'), { recursive: true, force: true })
  }
})

test('paste_only fails attachments outside configured attachment root', async () => {
  const input = new RecordingInputDriver()
  const clipboard = new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }))
  const fileClipboard = new RecordingFileClipboardController()
  const tempDir = path.join(os.tmpdir(), 'broadcast-runtime-test-outside-root')
  const attachmentRoot = path.join(tempDir, 'runtime', 'broadcast_attachments')
  const outsideDir = path.join(tempDir, 'runtime', 'broadcast_attachments-other')
  await fs.mkdir(outsideDir, { recursive: true })
  const outsidePath = path.join(outsideDir, 'asset-1_test.txt')
  await fs.writeFile(outsidePath, Buffer.from('real-data', 'utf8'))

  try {
    const result = await runPasteOnlyTask({
      action: 'paste_draft',
      idempotencyKey: 'paste-attachments-outside-root',
      requestDigest: 'digest-attachments-outside-root',
      conversationName: 'Customer A',
      draftText: 'First line\nSecond line',
      attachmentRoot,
      attachments: [
        {
          relativePath: path.join('..', 'broadcast_attachments-other', 'asset-1_test.txt'),
          filename: 'test.txt',
          size: (await fs.stat(outsidePath)).size,
          sha256: sha256('real-data'),
        },
      ],
    }, {
      input,
      clipboard,
      fileClipboard: fileClipboard as never,
      findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
      sleep: async () => undefined,
    } as never)

    assert.equal(result.status, 'failed')
    assert.equal(result.errorCode, 'ATTACHMENT_PATH_OUTSIDE_ROOT')
    assert.equal(result.attachmentsPrepared, false)
    assert.equal(result.attachmentPasteRequested, false)
    assert.deepEqual(input.events, [])
    assert.deepEqual(fileClipboard.writes, [])
  } finally {
    await fs.rm(tempDir, { recursive: true, force: true })
  }
})
