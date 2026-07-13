import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

export const PACKAGED_EXE_NAME = 'LangBot Desktop RPA Runtime.exe'
export const NATIVE_REBUILD_PREREQUISITES = [
  '@hurdlegroup/robotjs',
  'active-win',
  'node-window-manager',
]
// Windows Defender and Explorer can briefly hold the freshly generated executable
// while electron-builder is adding the ASAR integrity resource.  Keep the final
// output deterministic, but give those transient readers a realistic backoff.
export const TRANSIENT_PACKAGING_ATTEMPTS = 8

const scriptDir = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(scriptDir, '..')
const officialOutputRoot = resolve(projectRoot, 'dist-phase2-official')
const npmCommand = process.platform === 'win32' ? resolveExecutable('npm.cmd') : 'npm'
const electronBuilderCommand = process.platform === 'win32'
  ? resolve(projectRoot, 'node_modules', '.bin', 'electron-builder.cmd')
  : resolve(projectRoot, 'node_modules', '.bin', 'electron-builder')

export function getDeterministicDirOutputDir(root = projectRoot) {
  return resolve(root, 'dist-phase2-official', 'win-dir')
}

export function getDeterministicWinUnpackedDir(root = projectRoot) {
  return join(getDeterministicDirOutputDir(root), 'win-unpacked')
}

export function getDeterministicPackagedExePath(root = projectRoot) {
  return join(getDeterministicWinUnpackedDir(root), PACKAGED_EXE_NAME)
}

export function getReleaseOutputDir(root = projectRoot) {
  return resolve(root, 'dist-phase2-official', 'release')
}

export function getElectronBuilderArgs(mode = 'release', root = projectRoot) {
  if (mode === 'dir') {
    return ['--win', 'dir', `--config.directories.output=${getDeterministicDirOutputDir(root)}`]
  }
  return ['--win', 'portable', 'nsis', `--config.directories.output=${getReleaseOutputDir(root)}`]
}

export function resolveExecutable(command) {
  const result = execFileSync('where.exe', [command], {
    cwd: projectRoot,
    encoding: 'utf8',
    windowsHide: true,
  }).split(/\r?\n/).map((line) => line.trim()).find(Boolean)
  if (!result) throw new Error(`EXECUTABLE_NOT_FOUND ${command}`)
  return result
}

function run(command, args, options = {}) {
  const baseOptions = {
    cwd: projectRoot,
    stdio: 'inherit',
    windowsHide: true,
    ...options,
  }
  if (process.platform === 'win32' && /\.cmd$/i.test(command)) {
    execFileSync(command, args, {
      ...baseOptions,
      shell: true,
    })
    return
  }
  execFileSync(command, args, baseOptions)
}

function powershellJson(script) {
  const raw = execFileSync(
    'powershell',
    ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
    {
      cwd: projectRoot,
      encoding: 'utf8',
      windowsHide: true,
    },
  ).trim()
  if (!raw) return []
  const parsed = JSON.parse(raw)
  return Array.isArray(parsed) ? parsed : [parsed]
}

function listLockingProcesses(packagedExePath) {
  const escapedTarget = packagedExePath.replace(/'/g, "''")
  return powershellJson([
    `$target = '${escapedTarget}'`,
    '$processes = Get-CimInstance Win32_Process | Where-Object {',
    '  $_.ExecutablePath -and [string]::Equals($_.ExecutablePath, $target, [System.StringComparison]::OrdinalIgnoreCase)',
    '} | Select-Object ProcessId, Name, ExecutablePath, CommandLine',
    '$processes | ConvertTo-Json -Compress',
  ].join('; '))
}

function closeRuntimeProcesses(processes) {
  if (!processes.length) return
  const ids = processes
    .map((process) => Number(process.ProcessId))
    .filter((value) => Number.isFinite(value) && value > 0)
  if (!ids.length) return
  const joinedIds = ids.join(',')
  execFileSync(
    'powershell',
    [
      '-NoProfile',
      '-ExecutionPolicy',
      'Bypass',
      '-Command',
      [
        `$ids = @(${joinedIds})`,
        '$targets = Get-Process | Where-Object { $ids -contains $_.Id }',
        'foreach ($process in $targets) { try { if ($process.MainWindowHandle -ne 0) { [void]$process.CloseMainWindow() } } catch {} }',
        'Start-Sleep -Milliseconds 1500',
        '$remaining = Get-Process | Where-Object { $ids -contains $_.Id }',
        'foreach ($process in $remaining) { try { Stop-Process -Id $process.Id -Force } catch {} }',
      ].join('; '),
    ],
    {
      cwd: projectRoot,
      stdio: 'inherit',
      windowsHide: true,
    },
  )
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
}

function removeWithRetries(targetPath, retries = 10, waitMs = 1500) {
  if (!existsSync(targetPath)) return
  let lastError = null
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      rmSync(targetPath, { recursive: true, force: true })
      if (!existsSync(targetPath)) return
    } catch (error) {
      lastError = error
    }
    sleep(waitMs)
  }
  if (existsSync(targetPath)) {
    throw lastError ?? new Error(`FAILED_TO_REMOVE ${targetPath}`)
  }
}

function ensureOutputDirReady(outputDir, packagedExePath = null) {
  mkdirSync(officialOutputRoot, { recursive: true })
  if (packagedExePath) {
    const lockingProcesses = listLockingProcesses(packagedExePath)
    if (lockingProcesses.length) closeRuntimeProcesses(lockingProcesses)

    const remainingLocks = listLockingProcesses(packagedExePath)
    if (remainingLocks.length) {
      throw new Error(`OUTPUT_DIRECTORY_IN_USE ${JSON.stringify(remainingLocks)}`)
    }
  }

  removeWithRetries(outputDir)
}

function logNativeRebuildExpectations() {
  console.log(
    `[package-win] expected native rebuild prerequisites: ${NATIVE_REBUILD_PREREQUISITES.join(', ')}. `
    + 'Run `npm run rebuild:native` before packaging after dependency or Electron ABI changes.',
  )
}

export function packageWindowsRuntime(mode = 'release') {
  const builderArgs = getElectronBuilderArgs(mode, projectRoot)
  const outputDir = mode === 'dir' ? getDeterministicDirOutputDir(projectRoot) : getReleaseOutputDir(projectRoot)
  const packagedExePath = mode === 'dir' ? getDeterministicPackagedExePath(projectRoot) : null

  logNativeRebuildExpectations()
  run(npmCommand, ['run', 'build'])
  ensureOutputDirReady(outputDir, packagedExePath)
  const builderOptions = {
    env: {
      ...process.env,
      CSC_IDENTITY_AUTO_DISCOVERY: 'false',
    },
  }
  for (let attempt = 1; attempt <= TRANSIENT_PACKAGING_ATTEMPTS; attempt += 1) {
    try {
      run(electronBuilderCommand, builderArgs, builderOptions)
      return
    } catch (error) {
      if (attempt === TRANSIENT_PACKAGING_ATTEMPTS) throw error
      console.warn(`[package-win] electron-builder attempt ${attempt} failed; retrying deterministic output after a short delay.`)
      sleep(Math.min(15000, 3000 * attempt))
      ensureOutputDirReady(outputDir, packagedExePath)
    }
  }
}

function parseMode(argv) {
  return argv.includes('--dir-only') ? 'dir' : 'release'
}

const entrypointPath = fileURLToPath(import.meta.url)
const invokedPath = process.argv[1] ? resolve(process.argv[1]) : ''
if (invokedPath === entrypointPath) {
  packageWindowsRuntime(parseMode(process.argv.slice(2)))
}
