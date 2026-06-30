import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(scriptDir, '..')
const outputRootDir = resolve(projectRoot, 'dist-phase2-official')
const buildStamp = new Date().toISOString().replace(/[:.]/g, '-')
const outputDir = resolve(outputRootDir, buildStamp)
const packagedExePath = join(outputRootDir, 'win-unpacked', 'LangBot Desktop RPA Runtime.exe')
const npmCommand = process.platform === 'win32' ? resolveExecutable('npm.cmd') : 'npm'
const electronBuilderCommand = process.platform === 'win32'
  ? resolve(projectRoot, 'node_modules', '.bin', 'electron-builder.cmd')
  : resolve(projectRoot, 'node_modules', '.bin', 'electron-builder')

function resolveExecutable(command) {
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

function listLockingProcesses() {
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

function ensureOutputDirReady() {
  mkdirSync(outputRootDir, { recursive: true })
  const lockingProcesses = listLockingProcesses()
  if (lockingProcesses.length) closeRuntimeProcesses(lockingProcesses)

  const remainingLocks = listLockingProcesses()
  if (remainingLocks.length) {
    throw new Error(`OUTPUT_DIRECTORY_IN_USE ${JSON.stringify(remainingLocks)}`)
  }

  removeWithRetries(outputDir)
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

run(npmCommand, ['run', 'build'])
ensureOutputDirReady()
run(
  electronBuilderCommand,
  ['--win', 'portable', 'nsis', `--config.directories.output=${outputDir}`],
  {
    env: {
      ...process.env,
      CSC_IDENTITY_AUTO_DISCOVERY: 'false',
    },
  },
)
