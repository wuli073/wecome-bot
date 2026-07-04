import assert from 'node:assert/strict'
import test from 'node:test'
import { ClipboardController, type ClipboardAdapter } from '../src/main/input/clipboard-controller'
import type { InputDriver } from '../src/main/input/mouse-controller'
import { runPasteOnlyTask } from '../src/main/input/paste-controller'
import { RuntimeHost } from '../src/main/runtime/runtime-host'
import * as windowActivator from '../src/main/window/window-activator'
import * as windowFinder from '../src/main/window/window-finder'
import type { WindowDescriptor } from '../src/main/domain/window-types'

const wxworkWindow: WindowDescriptor = {
  appType: 'wework',
  windowId: 'w1',
  ownerWindowId: null,
  title: '????',
  executablePath: 'C:/Program Files/WXWork/WXWork.exe',
  processName: 'WXWork.exe',
  processId: 123,
  displayId: 1,
  boundsLogical: { x: 0, y: 0, width: 1000, height: 800 },
  clientBounds: { x: 0, y: 0, width: 1000, height: 800 },
  scaleFactor: 1,
  isVisible: true,
  isMinimized: false,
}

class RecordingInputDriver implements InputDriver {
  readonly events: Array<{ type: string; payload: unknown }> = []
  async click(point: { x: number; y: number }): Promise<void> { this.events.push({ type: 'click', payload: point }) }
  async hotkey(keys: string[]): Promise<void> { this.events.push({ type: 'hotkey', payload: keys }) }
  async typeText(text: string): Promise<void> { this.events.push({ type: 'typeText', payload: text }) }
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
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, executablePath: '', processName: '', title: 'Customer A - wecom' }), true)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, ownerWindowId: 'parent' }), true)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, executablePath: 'C:/Program Files/WXWork/WXWorkWeb.exe', processName: 'WXWorkWeb.exe' }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, executablePath: 'C:/Program Files/WXWork/WeChatAppEx.exe', processName: 'WeChatAppEx.exe' }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, isVisible: false }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, clientBounds: { x: 0, y: 0, width: 99, height: 800 } }), false)
  assert.equal(windowFinder.isValidVisibleWxWorkMainWindow({ ...wxworkWindow, clientBounds: { x: 0, y: 0, width: 1000, height: 99 } }), false)
})

test('current active WXWork window is used directly for paste_only', () => {
  const resolvePasteOnlyWxWorkWindow = (windowFinder as Record<string, unknown>).resolvePasteOnlyWxWorkWindow
  assert.equal(typeof resolvePasteOnlyWxWorkWindow, 'function')

  const result = (resolvePasteOnlyWxWorkWindow as Function)(
    { ...wxworkWindow, windowId: 'active', title: 'Customer A' },
    [{ ...wxworkWindow, windowId: 'fallback', title: '????' }],
  )

  assert.equal(result.ok, true)
  if (result.ok) {
    assert.equal(result.window.windowId, 'active')
  }
})

test('non-WXWork active window falls back to exact ???? title from window list', () => {
  const resolvePasteOnlyWxWorkWindow = (windowFinder as Record<string, unknown>).resolvePasteOnlyWxWorkWindow
  assert.equal(typeof resolvePasteOnlyWxWorkWindow, 'function')

  const result = (resolvePasteOnlyWxWorkWindow as Function)(
    { ...wxworkWindow, appType: 'chrome', title: 'Docs', processName: 'chrome.exe', executablePath: 'C:/Program Files/Google/Chrome/chrome.exe' },
    [
      { ...wxworkWindow, windowId: 'first', title: 'Customer A' },
      { ...wxworkWindow, windowId: 'exact', title: '????' },
    ],
  )

  assert.equal(result.ok, true)
  if (result.ok) {
    assert.equal(result.window.windowId, 'exact')
  }
})

test('single valid WXWork window is selected for the pure keyboard paste_only path', () => {
  const candidates = windowFinder.collectVisibleWxWorkMainWindows([
    { ...wxworkWindow, executablePath: 'C:/Program Files/WXWork/WXWorkWeb.exe', processName: 'WXWorkWeb.exe', windowId: 'web' },
    { ...wxworkWindow, executablePath: '', processName: 'WXWork', ownerWindowId: 'owner-kept', windowId: 'main' },
  ])

  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow(candidates)
  assert.equal(selection.ok, true)
  if (selection.ok) {
    assert.equal(selection.window.windowId, 'main')
  }
})

test('same WXWork process with multiple HWNDs is not treated as ambiguous', () => {
  const candidates = windowFinder.collectVisibleWxWorkMainWindows([
    { ...wxworkWindow, executablePath: '', processName: 'WXWork', windowId: 'main-1', processId: 456, title: 'Customer A' },
    { ...wxworkWindow, executablePath: 'D:/WXWork/WXWork.exe', processName: 'WXWork.exe', windowId: 'main-2', processId: 456, title: 'Customer B' },
  ])

  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow(candidates)
  assert.equal(selection.ok, true)
  if (selection.ok) {
    assert.equal(selection.window.windowId, 'main-1')
  }
})

test('exact ???? title is preferred when multiple usable WXWork windows exist', () => {
  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow([
    { ...wxworkWindow, windowId: 'first', title: 'Customer A' },
    { ...wxworkWindow, windowId: 'exact', title: '????' },
    { ...wxworkWindow, windowId: 'third', title: 'Customer B' },
  ])

  assert.equal(selection.ok, true)
  if (selection.ok) {
    assert.equal(selection.window.windowId, 'exact')
  }
})

test('first usable WXWork window is selected when no exact ???? title exists', () => {
  const selection = windowFinder.resolveUniqueVisibleWxWorkMainWindow([
    { ...wxworkWindow, windowId: 'first', title: 'Customer A' },
    { ...wxworkWindow, windowId: 'second', title: 'Customer B' },
  ])

  assert.equal(selection.ok, true)
  if (selection.ok) {
    assert.equal(selection.window.windowId, 'first')
  }
})

test('paste_only blocks when no valid WXWork main window is found', async () => {
  const input = new RecordingInputDriver()
  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p0',
    requestDigest: 'd0',
    conversationName: 'Customer A',
    draftText: 'hello',
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

test('paste_only executes fixed keyboard sequence exactly once and never sends', async () => {
  const input = new RecordingInputDriver()
  const sleeps: number[] = []
  const clipboard = new ClipboardController(undefined, fakeClipboardAdapter(['text/plain'], { text: 'old clipboard' }))

  const result = await runPasteOnlyTask({
    action: 'paste_draft',
    idempotencyKey: 'p1',
    requestDigest: 'd1',
    conversationName: 'Customer A',
    draftText: 'hello draft',
  }, {
    input,
    clipboard,
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async (ms) => { sleeps.push(ms) },
  })

  assert.equal(result.status, 'interrupted')
  assert.equal(result.stage, 'paste_verification_unavailable')
  assert.deepEqual(sleeps, [400, 400, 1000])
  assert.deepEqual(input.events, [
    { type: 'hotkey', payload: ['Control', 'F'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
    { type: 'hotkey', payload: ['Enter'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
  ])
  assert.equal(result.searchShortcutCount, 1)
  assert.equal(result.conversationPasteCount, 1)
  assert.equal(result.conversationConfirmEnterCount, 1)
  assert.equal(result.draftPasteCount, 1)
  assert.equal(result.sendKeyCount, 0)
  assert.equal(result.messageSent, false)
  assert.equal(result.contentVerified, false)
  assert.equal(result.verificationFailed, true)
  assert.equal(result.draftWritten, false)
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
      return { ...wxworkWindow, windowId: 'focused' }
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
    getActiveWindowDescriptor: async () => ({ ...wxworkWindow, windowId: 'already-active' }),
  })

  assert.equal(result.ok, true)
  assert.deepEqual(calls, [])
})

test('managed window activation succeeds when polling reaches a different WXWork HWND', async () => {
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

  assert.equal(result.ok, true)
  if (result.ok) {
    assert.equal(result.window?.windowId, 'target-b')
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
    draftText: 'hello draft',
  }, {
    input: new RecordingInputDriver(),
    clipboard: new FailingClipboard({ formats: ['text'], data: { text: 'old' } }),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
    verifyPasteContent: async () => ({
      ok: true,
      inputLocated: true,
      draftWritten: true,
      contentVerified: true,
    }),
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
    draftText: 'hello draft',
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
    draftText: 'hello draft',
  }, {
    input,
    clipboard,
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
    verifyPasteContent: async () => ({
      ok: true,
      inputLocated: true,
      draftWritten: true,
      contentVerified: true,
    }),
  } as never)

  assert.equal(result.status, 'succeeded')
  assert.equal(result.stage, 'pasted_to_input')
  assert.equal(result.inputLocated, true)
  assert.equal(result.draftWritten, true)
  assert.equal(result.contentVerified, true)
  assert.equal(result.verificationFailed, false)
  assert.deepEqual(input.events, [
    { type: 'hotkey', payload: ['Control', 'F'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
    { type: 'hotkey', payload: ['Enter'] },
    { type: 'hotkey', payload: ['Control', 'V'] },
  ])
})

test('runtime host reuses idempotency key and does not repeat paste task', async () => {
  const input = new RecordingInputDriver()
  const host = new RuntimeHost({
    input,
    clipboard: new ClipboardController({ formats: ['text'], data: { text: 'old' } }),
    findTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    activateTargetWindow: async () => ({ ok: true, window: wxworkWindow }),
    sleep: async () => undefined,
  })
  const request = {
    action: 'paste_draft' as const,
    idempotencyKey: 'idem-1',
    requestDigest: 'digest-1',
    conversationName: 'Customer A',
    draftText: 'hello',
  }
  const first = await host.createTask(request)
  const second = await host.createTask({ ...request, draftText: 'changed' })
  assert.equal(first.id, second.id)
  assert.equal(input.events.filter((event) => event.type === 'hotkey').length, 4)
})
