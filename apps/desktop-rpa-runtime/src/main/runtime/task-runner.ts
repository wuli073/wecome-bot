import type { RuntimeTaskRequest } from '../domain/task-types'
import type { WindowDescriptor } from '../domain/window-types'
import { ClipboardController } from '../input/clipboard-controller'
import { RobotInputDriver, type InputDriver } from '../input/mouse-controller'
import { runPasteOnlyTask } from '../input/paste-controller'
import { runSendDraftTask } from '../input/send-controller'
import { activateWindow } from '../window/window-activator'
import { findUniqueVisibleWxWorkMainWindow } from '../window/window-finder'

type TargetWindowResult =
  | { ok: true; window: WindowDescriptor }
  | { ok: false; errorCode: 'TARGET_WINDOW_NOT_FOUND'; candidates: WindowDescriptor[] }

export interface TaskRunnerOptions {
  runtimeAutoSendEnabled?: boolean
  input?: InputDriver
  clipboard?: ClipboardController
  sleep?: (ms: number) => Promise<void>
  findTargetWindow?: () => Promise<TargetWindowResult>
  activateTargetWindow?: (window: WindowDescriptor) => Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }>
  sendDriverForceDisabled?: boolean
}

export class TaskRunner {
  readonly input: InputDriver
  readonly clipboard: ClipboardController
  private readonly runtimeAutoSendEnabled: boolean
  private readonly sendDriverForceDisabled: boolean
  private readonly sleep?: (ms: number) => Promise<void>
  private readonly findTargetWindow: () => Promise<TargetWindowResult>
  private readonly activateTargetWindow: (window: WindowDescriptor) => Promise<{ ok: boolean; errorCode?: string; window?: WindowDescriptor }>

  constructor(options: TaskRunnerOptions = {}) {
    this.runtimeAutoSendEnabled = Boolean(options.runtimeAutoSendEnabled)
    this.input = options.input ?? new RobotInputDriver()
    this.clipboard = options.clipboard ?? new ClipboardController()
    this.sendDriverForceDisabled = Boolean(options.sendDriverForceDisabled)
    this.sleep = options.sleep
    this.findTargetWindow = options.findTargetWindow ?? findUniqueVisibleWxWorkMainWindow
    this.activateTargetWindow = options.activateTargetWindow ?? activateWindow
  }

  async run(request: RuntimeTaskRequest): Promise<Record<string, unknown>> {
    if (request.action === 'paste_draft') {
      return runPasteOnlyTask(request, {
        clipboard: this.clipboard,
        input: this.input,
        sleep: this.sleep,
        findTargetWindow: this.findTargetWindow,
        activateTargetWindow: this.activateTargetWindow,
      })
    }
    if (request.action === 'send_draft') {
      return runSendDraftTask(request, {
        input: this.input,
        runtimeAutoSendEnabled: this.runtimeAutoSendEnabled,
        sendDriverForceDisabled: this.sendDriverForceDisabled,
      })
    }
    return { status: 'blocked', stage: `${request.action}_disabled`, errorCode: 'UNSUPPORTED_TASK_ACTION', messageSent: false }
  }
}
