import type { RuntimeTaskRequest } from '../domain/task-types'
import type { WindowDescriptor } from '../domain/window-types'
import { ClipboardController } from '../input/clipboard-controller'
import { WindowsFileClipboardController, type FileClipboardController } from '../input/file-clipboard-controller'
import { RobotInputDriver, type InputDriver } from '../input/mouse-controller'
import { runPasteOnlyTask } from '../input/paste-controller'
import type {
  PasteVerificationProvider,
  PasteVerificationCapability,
} from '../input/paste-verification'
import { runSendMessageTask } from '../input/send-controller'
import { activateWindow } from '../window/window-activator'
import { findUniqueVisibleWxWorkMainWindow, getActiveWindowDescriptor } from '../window/window-finder'
import type { WxWorkWindowSelectionDiagnostics } from '../window/window-finder'

type TargetWindowResult =
  | { ok: true; window: WindowDescriptor }
  | {
      ok: false
      errorCode: 'TARGET_WINDOW_NOT_FOUND' | 'TARGET_WINDOW_AMBIGUOUS'
      candidates: WindowDescriptor[]
      diagnostics?: WxWorkWindowSelectionDiagnostics
    }

export interface TaskRunnerOptions {
  runtimeAutoSendEnabled?: boolean
  input?: InputDriver
  clipboard?: ClipboardController
  sleep?: (ms: number) => Promise<void>
  findTargetWindow?: () => Promise<TargetWindowResult>
  activateTargetWindow?: (window: WindowDescriptor) => Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }>
  fileClipboard?: FileClipboardController
  getActiveWindow?: () => Promise<WindowDescriptor | null>
  pasteVerificationCapability?: PasteVerificationCapability
  pasteVerificationProvider?: PasteVerificationProvider
  sendDriverForceDisabled?: boolean
}

export class TaskRunner {
  readonly input: InputDriver
  readonly clipboard: ClipboardController
  readonly fileClipboard: FileClipboardController
  private readonly runtimeAutoSendEnabled: boolean
  private readonly sendDriverForceDisabled: boolean
  private readonly sleep?: (ms: number) => Promise<void>
  private readonly findTargetWindow: () => Promise<TargetWindowResult>
  private readonly activateTargetWindow: (window: WindowDescriptor) => Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }>
  private readonly getActiveWindow: () => Promise<WindowDescriptor | null>
  private readonly getPasteVerificationCapabilityInternal: () => PasteVerificationCapability
  private readonly refreshPasteVerificationCapabilityInternal: (force?: boolean) => Promise<PasteVerificationCapability>
  private readonly pasteVerificationProvider?: PasteVerificationProvider

  constructor(options: TaskRunnerOptions = {}) {
    this.runtimeAutoSendEnabled = Boolean(options.runtimeAutoSendEnabled)
    this.input = options.input ?? new RobotInputDriver()
    this.clipboard = options.clipboard ?? new ClipboardController()
    this.fileClipboard = options.fileClipboard ?? new WindowsFileClipboardController()
    this.sendDriverForceDisabled = Boolean(options.sendDriverForceDisabled)
    this.sleep = options.sleep
    this.findTargetWindow = options.findTargetWindow ?? findUniqueVisibleWxWorkMainWindow
    this.activateTargetWindow = options.activateTargetWindow ?? activateWindow
    this.getActiveWindow = options.getActiveWindow ?? getActiveWindowDescriptor
    this.pasteVerificationProvider = options.pasteVerificationProvider
    if (options.pasteVerificationCapability || options.pasteVerificationProvider) {
      const staticCapability = options.pasteVerificationCapability
        ? options.pasteVerificationCapability as PasteVerificationCapability
        : {
            available: false,
            reason: 'PASTE_VERIFICATION_DISABLED',
            method: 'unavailable',
            requiresManualConversationOpen: false,
            supportedErrorCodes: [],
          }
      const injectedProvider = options.pasteVerificationProvider
      this.getPasteVerificationCapabilityInternal = injectedProvider?.getCapability ?? (() => staticCapability)
      this.refreshPasteVerificationCapabilityInternal = injectedProvider?.refreshCapability
        ? async (force = false) => injectedProvider.refreshCapability!(force)
        : async () => staticCapability
      return
    }

    this.getPasteVerificationCapabilityInternal = () => ({
      available: false,
      reason: 'PASTE_VERIFICATION_DISABLED',
      method: 'unavailable',
      requiresManualConversationOpen: false,
      supportedErrorCodes: [],
    })
    this.refreshPasteVerificationCapabilityInternal = async () => this.getPasteVerificationCapabilityInternal()
  }

  async run(request: RuntimeTaskRequest, options?: { isCancelled?: () => boolean }): Promise<Record<string, unknown>> {
    if (request.action === 'paste_draft') {
      return runPasteOnlyTask(request, {
        clipboard: this.clipboard,
        input: this.input,
        sleep: this.sleep,
        findTargetWindow: this.findTargetWindow,
        activateTargetWindow: this.activateTargetWindow,
        fileClipboard: this.fileClipboard,
        getActiveWindow: this.getActiveWindow,
        isCancelled: options?.isCancelled,
        pasteVerificationProvider: this.pasteVerificationProvider,
      })
    }
    if (request.action === 'send_draft' || request.action === 'send_message') {
      return runSendMessageTask(request, {
        clipboard: this.clipboard,
        input: this.input,
        runtimeAutoSendEnabled: this.runtimeAutoSendEnabled,
        sendDriverForceDisabled: this.sendDriverForceDisabled,
        sleep: this.sleep,
        findTargetWindow: this.findTargetWindow,
        activateTargetWindow: this.activateTargetWindow,
        fileClipboard: this.fileClipboard,
        getActiveWindow: this.getActiveWindow,
        isCancelled: options?.isCancelled,
        pasteVerificationProvider: this.pasteVerificationProvider,
      })
    }
    return { status: 'blocked', stage: `${request.action}_disabled`, errorCode: 'UNSUPPORTED_TASK_ACTION', messageSent: false }
  }

  getPasteVerificationCapability(): PasteVerificationCapability {
    return this.getPasteVerificationCapabilityInternal()
  }

  async refreshPasteVerificationCapability(force = false): Promise<PasteVerificationCapability> {
    return this.refreshPasteVerificationCapabilityInternal(force)
  }
}
