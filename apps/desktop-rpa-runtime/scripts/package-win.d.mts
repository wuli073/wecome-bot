export const PACKAGED_EXE_NAME: string
export const NATIVE_REBUILD_PREREQUISITES: string[]
export const TRANSIENT_PACKAGING_ATTEMPTS: number

export function getDeterministicDirOutputDir(root?: string): string
export function getDeterministicWinUnpackedDir(root?: string): string
export function getDeterministicPackagedExePath(root?: string): string
export function getReleaseOutputDir(root?: string): string
export function getElectronBuilderArgs(mode?: 'release' | 'dir', root?: string): string[]
export function resolveExecutable(command: string): string
export function packageWindowsRuntime(mode?: 'release' | 'dir'): void
