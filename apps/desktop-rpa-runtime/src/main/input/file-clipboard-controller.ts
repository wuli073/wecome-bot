import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import type { RuntimeAttachmentPayload } from '../domain/task-types'

const CLIPBOARD_RETRY_DELAYS_MS = [80, 120, 180, 250, 350, 500] as const
const HELPER_TIMEOUT_MS = 10_000
const MAX_OUTPUT_BYTES = 32 * 1024
const CLIPBOARD_FORMAT_CF_HDROP = 'CF_HDROP'

const POWERSHELL_FILE_CLIPBOARD_SCRIPT = `
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Write-Failure([string]$Code, [string]$Message) {
  [Console]::WriteLine(([PSCustomObject]@{
    ok = $false
    errorCode = $Code
    sanitizedMessage = $Message
  } | ConvertTo-Json -Compress))
  exit 1
}

function Test-ClipboardBusyException([System.Exception]$Exception) {
  if ($null -eq $Exception) { return $false }
  if ($Exception -is [System.Runtime.InteropServices.ExternalException]) { return $true }
  if ($null -ne $Exception.InnerException) {
    return Test-ClipboardBusyException $Exception.InnerException
  }
  return $false
}

function Invoke-ClipboardWithRetry([scriptblock]$Action) {
  $delays = @(80, 120, 180, 250, 350, 500)
  for ($attempt = 0; $attempt -lt $delays.Count + 1; $attempt++) {
    try {
      return & $Action
    } catch {
      if (-not (Test-ClipboardBusyException $_.Exception)) {
        throw
      }
      if ($attempt -ge $delays.Count) {
        throw
      }
      Start-Sleep -Milliseconds $delays[$attempt]
    }
  }
}

try {
  $raw = [Console]::In.ReadToEnd()
  if ([string]::IsNullOrWhiteSpace($raw)) {
    Write-Failure 'FILE_CLIPBOARD_HELPER_FAILED' 'Unable to prepare the file clipboard'
  }
  $payload = $raw | ConvertFrom-Json
  $files = @($payload.files)
  $expectedCount = [int]$payload.expectedCount
  if ($files.Count -le 0) {
    Write-Failure 'FILE_CLIPBOARD_HELPER_FAILED' 'Unable to prepare the file clipboard'
  }
  if ($expectedCount -ne $files.Count) {
    Write-Failure 'FILE_CLIPBOARD_HELPER_FAILED' 'Unable to prepare the file clipboard'
  }

  $normalizedExpected = New-Object System.Collections.Generic.List[string]
  $stringCollection = New-Object System.Collections.Specialized.StringCollection
  foreach ($file in $files) {
    $path = [string]$file
    if ([string]::IsNullOrWhiteSpace($path) -or -not [System.IO.Path]::IsPathRooted($path)) {
      Write-Failure 'FILE_CLIPBOARD_HELPER_FAILED' 'Unable to prepare the file clipboard'
    }
    if (-not [System.IO.File]::Exists($path)) {
      Write-Failure 'FILE_CLIPBOARD_HELPER_FAILED' 'Unable to prepare the file clipboard'
    }
    $item = Get-Item -LiteralPath $path -Force
    if ($item.PSIsContainer) {
      Write-Failure 'FILE_CLIPBOARD_HELPER_FAILED' 'Unable to prepare the file clipboard'
    }
    $fullPath = [System.IO.Path]::GetFullPath($item.FullName)
    [void]$normalizedExpected.Add($fullPath)
    [void]$stringCollection.Add($fullPath)
  }

  $dataObject = New-Object System.Windows.Forms.DataObject
  $dataObject.SetFileDropList($stringCollection)
  Invoke-ClipboardWithRetry { [System.Windows.Forms.Clipboard]::SetDataObject($dataObject, $true) } | Out-Null
  $observed = Invoke-ClipboardWithRetry { [System.Windows.Forms.Clipboard]::GetFileDropList() }

  $observedPaths = New-Object System.Collections.Generic.List[string]
  foreach ($path in $observed) {
    [void]$observedPaths.Add([System.IO.Path]::GetFullPath([string]$path))
  }

  $pathsMatched = $normalizedExpected.Count -eq $observedPaths.Count
  if ($pathsMatched) {
    for ($i = 0; $i -lt $normalizedExpected.Count; $i++) {
      if (-not [string]::Equals($normalizedExpected[$i], $observedPaths[$i], [System.StringComparison]::OrdinalIgnoreCase)) {
        $pathsMatched = $false
        break
      }
    }
  }

  [Console]::WriteLine(([PSCustomObject]@{
    ok = $true
    clipboardFormat = 'CF_HDROP'
    expectedCount = $normalizedExpected.Count
    observedCount = $observedPaths.Count
    pathsMatched = $pathsMatched
  } | ConvertTo-Json -Compress))

  if (-not $pathsMatched) {
    exit 2
  }
  exit 0
} catch {
  Write-Failure 'FILE_CLIPBOARD_HELPER_FAILED' 'Unable to prepare the file clipboard'
}
`

export interface FileClipboardPrepareRequest {
  files: RuntimeAttachmentPayload[]
}

export interface FileClipboardPrepareResult {
  ok: true
  clipboardFormat: 'CF_HDROP'
  expectedCount: number
  observedCount: number
  pathsMatched: true
}

export interface FileClipboardController {
  writeFiles(files: RuntimeAttachmentPayload[]): Promise<FileClipboardPrepareResult>
}

export interface FileClipboardHelperPayload {
  files: string[]
  expectedCount: number
}

export interface FileClipboardHelperSuccessOutput {
  ok: true
  clipboardFormat: string
  expectedCount: number
  observedCount: number
  pathsMatched: boolean
}

export interface FileClipboardHelperFailureOutput {
  ok: false
  errorCode: string
  sanitizedMessage: string
}

export type FileClipboardHelperOutput =
  | FileClipboardHelperSuccessOutput
  | FileClipboardHelperFailureOutput

export interface FileClipboardSpawnResult {
  stdout: string
  stderr: string
  exitCode: number | null
  timedOut: boolean
}

export interface SpawnController {
  (
    command: string,
    args: string[],
    options: {
      shell: false
      windowsHide: true
      stdio: ['pipe', 'pipe', 'pipe']
    },
  ): ChildProcessWithoutNullStreams
}

export function getFileClipboardPowerShellScript(): string {
  return POWERSHELL_FILE_CLIPBOARD_SCRIPT
}

export function encodePowerShellCommandUtf16Le(script: string): string {
  return Buffer.from(script, 'utf16le').toString('base64')
}

export function buildFileClipboardHelperPayload(files: RuntimeAttachmentPayload[]): FileClipboardHelperPayload {
  const resolvedPaths = files.map((item) => String(item.resolvedPath || '').trim())
  return {
    files: resolvedPaths,
    expectedCount: resolvedPaths.length,
  }
}

export function stringifyFileClipboardHelperPayload(payload: FileClipboardHelperPayload): string {
  return JSON.stringify(payload)
}

export function buildFileClipboardHelperArgs(script: string): string[] {
  return [
    '-NoLogo',
    '-NoProfile',
    '-NonInteractive',
    '-STA',
    '-WindowStyle',
    'Hidden',
    '-EncodedCommand',
    encodePowerShellCommandUtf16Le(script),
  ]
}

export function parseFileClipboardHelperOutput(
  stdout: string,
  expectedCount: number,
): FileClipboardPrepareResult {
  const trimmed = stdout.trim()
  if (!trimmed) {
    throw new Error('FILE_CLIPBOARD_OUTPUT_INVALID')
  }
  const lines = trimmed.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (lines.length !== 1) {
    throw new Error('FILE_CLIPBOARD_OUTPUT_INVALID')
  }

  let parsed: FileClipboardHelperOutput
  try {
    parsed = JSON.parse(lines[0]) as FileClipboardHelperOutput
  } catch {
    throw new Error('FILE_CLIPBOARD_OUTPUT_INVALID')
  }

  if (!parsed || typeof parsed !== 'object' || parsed.ok !== true) {
    if (parsed && typeof parsed === 'object' && parsed.ok === false && parsed.errorCode) {
      throw new Error(String(parsed.errorCode))
    }
    throw new Error('FILE_CLIPBOARD_HELPER_FAILED')
  }
  if (parsed.clipboardFormat !== CLIPBOARD_FORMAT_CF_HDROP) {
    throw new Error('FILE_CLIPBOARD_OUTPUT_INVALID')
  }
  if (parsed.expectedCount !== expectedCount || parsed.observedCount !== expectedCount) {
    throw new Error(
      parsed.expectedCount !== expectedCount
        ? 'FILE_CLIPBOARD_COUNT_MISMATCH'
        : 'FILE_CLIPBOARD_COUNT_MISMATCH',
    )
  }
  if (parsed.pathsMatched !== true) {
    throw new Error('FILE_CLIPBOARD_PATH_MISMATCH')
  }

  return {
    ok: true,
    clipboardFormat: CLIPBOARD_FORMAT_CF_HDROP,
    expectedCount: parsed.expectedCount,
    observedCount: parsed.observedCount,
    pathsMatched: true,
  }
}

export function computeAttachmentPostPasteDelayMs(totalSizeBytes: number): number {
  const base = 1000
  const increment = Math.ceil(Math.max(0, totalSizeBytes) / (10 * 1024 * 1024)) * 300
  return Math.min(base + increment, 3000)
}

function sanitizeStderr(stderr: string): string {
  return stderr
    .replace(/[A-Za-z]:\\[^\r\n\t ]+/g, '[redacted-path]')
    .replace(/\/[^\r\n\t ]+/g, (value) => (value.includes(':') ? '[redacted-path]' : value))
    .slice(0, 500)
}

async function runFileClipboardHelper(
  child: ChildProcessWithoutNullStreams,
  stdinPayload: string,
): Promise<FileClipboardSpawnResult> {
  const stdoutChunks: Buffer[] = []
  const stderrChunks: Buffer[] = []
  let stdoutBytes = 0
  let stderrBytes = 0
  let timedOut = false

  const appendChunk = (chunks: Buffer[], chunk: Buffer, currentBytes: number) => {
    if (currentBytes >= MAX_OUTPUT_BYTES) return currentBytes
    const remaining = MAX_OUTPUT_BYTES - currentBytes
    const next = chunk.byteLength > remaining ? chunk.subarray(0, remaining) : chunk
    chunks.push(Buffer.from(next))
    return currentBytes + next.byteLength
  }

  const timer = setTimeout(() => {
    timedOut = true
    child.kill()
  }, HELPER_TIMEOUT_MS)

  child.stdout.on('data', (chunk) => {
    stdoutBytes = appendChunk(stdoutChunks, Buffer.from(chunk), stdoutBytes)
  })
  child.stderr.on('data', (chunk) => {
    stderrBytes = appendChunk(stderrChunks, Buffer.from(chunk), stderrBytes)
  })

  const closePromise = new Promise<FileClipboardSpawnResult>((resolve, reject) => {
    child.once('error', reject)
    child.once('close', (code) => {
      clearTimeout(timer)
      resolve({
        stdout: Buffer.concat(stdoutChunks).toString('utf8'),
        stderr: sanitizeStderr(Buffer.concat(stderrChunks).toString('utf8')),
        exitCode: code,
        timedOut,
      })
    })
  })

  child.stdin.write(Buffer.from(stdinPayload, 'utf8'))
  child.stdin.end()
  return closePromise
}

export class WindowsFileClipboardController implements FileClipboardController {
  constructor(
    private readonly spawnProcess: SpawnController = spawn as SpawnController,
  ) {}

  async writeFiles(files: RuntimeAttachmentPayload[]): Promise<FileClipboardPrepareResult> {
    if (files.length === 0) {
      throw new Error('FILE_CLIPBOARD_HELPER_FAILED')
    }

    const payload = buildFileClipboardHelperPayload(files)
    const stdinPayload = stringifyFileClipboardHelperPayload(payload)

    let child: ChildProcessWithoutNullStreams
    try {
      child = this.spawnProcess(
        'powershell.exe',
        buildFileClipboardHelperArgs(getFileClipboardPowerShellScript()),
        {
          shell: false,
          windowsHide: true,
          stdio: ['pipe', 'pipe', 'pipe'],
        },
      )
    } catch {
      throw new Error('FILE_CLIPBOARD_HELPER_SPAWN_FAILED')
    }

    let result: FileClipboardSpawnResult
    try {
      result = await runFileClipboardHelper(child, stdinPayload)
    } catch (error) {
      const nodeCode = typeof error === 'object' && error !== null && 'code' in error
        ? String((error as { code?: string }).code || '')
        : ''
      if (nodeCode === 'ENOENT') {
        throw new Error('FILE_CLIPBOARD_HELPER_SPAWN_FAILED')
      }
      throw error
    }

    if (result.timedOut) {
      throw new Error('FILE_CLIPBOARD_HELPER_TIMEOUT')
    }
    if (result.stdout.length >= MAX_OUTPUT_BYTES || result.stderr.length >= MAX_OUTPUT_BYTES) {
      throw new Error('FILE_CLIPBOARD_OUTPUT_INVALID')
    }
    if (result.exitCode !== 0) {
      if (result.stdout.trim()) {
        try {
          parseFileClipboardHelperOutput(result.stdout, payload.expectedCount)
        } catch (error) {
          const message = error instanceof Error ? error.message : ''
          if (message) throw error
        }
      }
      throw new Error('FILE_CLIPBOARD_HELPER_FAILED')
    }

    return parseFileClipboardHelperOutput(result.stdout, payload.expectedCount)
  }
}

export { CLIPBOARD_RETRY_DELAYS_MS, HELPER_TIMEOUT_MS, MAX_OUTPUT_BYTES }
