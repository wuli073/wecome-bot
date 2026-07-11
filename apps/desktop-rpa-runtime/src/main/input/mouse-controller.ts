import { createRequire } from 'node:module'
import { getElectron } from '../electron-runtime'

export interface InputDriver {
  click(point: { x: number; y: number }): Promise<void>
  hotkey(keys: string[]): Promise<void>
  typeText?(text: string): Promise<void>
}

interface RobotModule {
  moveMouse(x: number, y: number): void
  mouseClick(button?: 'left' | 'right' | 'middle', double?: boolean): void
  keyTap(key: string, modifier?: string | string[]): void
  typeString(text: string): void
}

const require = createRequire(import.meta.url)
let robotInstance: RobotModule | null = null

function getRobot(): RobotModule {
  robotInstance ??= require('@hurdlegroup/robotjs') as RobotModule
  return robotInstance
}

function normalizeKey(key: string): string {
  const normalized = key.trim().toLowerCase()
  if (normalized === 'control' || normalized === 'ctrl') return 'control'
  if (normalized === 'cmd' || normalized === 'command' || normalized === 'meta') return 'command'
  if (normalized === 'return') return 'enter'
  return normalized
}

export function logicalPointToPhysical(point: { x: number; y: number }): { x: number; y: number } {
  try {
    const { screen } = getElectron()
    if (screen?.dipToScreenPoint) return screen.dipToScreenPoint(point)
  } catch {
    // Fall back to the provided point when Electron is unavailable in tests.
  }
  return point
}

export class RobotInputDriver implements InputDriver {
  async click(point: { x: number; y: number }): Promise<void> {
    const robot = getRobot()
    const physical = logicalPointToPhysical(point)
    robot.moveMouse(Math.round(physical.x), Math.round(physical.y))
    robot.mouseClick('left', false)
  }

  async hotkey(keys: string[]): Promise<void> {
    const normalized = keys.map(normalizeKey)
    const key = normalized.at(-1)
    if (!key) return
    const modifiers = normalized.slice(0, -1)
    getRobot().keyTap(key, modifiers)
  }

  async typeText(text: string): Promise<void> {
    getRobot().typeString(text)
  }
}
