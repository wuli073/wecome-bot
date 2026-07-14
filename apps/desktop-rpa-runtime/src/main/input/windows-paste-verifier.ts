import { execFile } from 'node:child_process'
import { createHash } from 'node:crypto'
import { promises as fs } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { promisify } from 'node:util'
import type {
  PasteVerificationArgs,
  PasteVerificationCapability,
  PasteVerificationProvider,
  PasteInputObservationResult,
  PowerShellStderrCategory,
  TaskVerificationDiagnostic,
  TaskVerificationFailureStep,
} from './paste-verification'

const execFileAsync = promisify(execFile)
const VERIFICATION_METHOD = 'windows_uia'
const PASTE_VERIFICATION_UNAVAILABLE = 'PASTE_VERIFICATION_UNAVAILABLE'
const UIA_DIAGNOSTIC_CODES = {
  powershellNotFound: 'POWERSHELL_NOT_FOUND',
  assemblyLoadFailed: 'UIA_ASSEMBLY_LOAD_FAILED',
  rootUnavailable: 'UIA_ROOT_UNAVAILABLE',
  probeTimeout: 'UIA_PROBE_TIMEOUT',
  outputInvalid: 'UIA_OUTPUT_INVALID',
  probeFailed: 'UIA_PROBE_FAILED',
} as const
const SUPPORTED_ERROR_CODES = [
  'TARGET_WINDOW_CHANGED',
  'INPUT_NOT_LOCATED',
  'PASTE_CONTENT_MISMATCH',
  'UIA_TASK_SCRIPT_FAILED',
  PASTE_VERIFICATION_UNAVAILABLE,
  'TARGET_GROUP_NOT_FOUND',
  'TARGET_GROUP_AMBIGUOUS',
] as const
const DEFAULT_PROBE_TTL_MS = 30_000
const DEFAULT_COMMAND_TIMEOUT_MS = 8_000
const CLEANUP_RETRY_DELAYS_MS = [50, 150, 300] as const
const WINDOW_STABILIZATION_RETRY_DELAYS_MS = [120, 180, 250] as const
const STARTUP_ERROR_CODES = new Set(['ENOENT', 'EACCES', 'EPERM', 'UNKNOWN'])

type RawVerifierPayload = {
  activeWindowHandle?: string | number | null
  activeOwnerWindowHandle?: string | number | null
  activeRootOwnerWindowHandle?: string | number | null
  activeProcessId?: number | null
  activeExecutablePath?: string | null
  activeWindowTitle?: string | null
  activeWindowClassName?: string | null
  activeRootOwnerWindowTitle?: string | null
  activeRootOwnerWindowClassName?: string | null
  conversationCandidates?: string[] | null
  inputLocated?: boolean
  actualText?: string | null
}

type RawAvailabilityPayload = {
  ok?: boolean
  errorCode?: string | null
}

type ScriptErrorPayload = {
  ok?: boolean
  errorCode?: string | null
  failureStep?: TaskVerificationFailureStep | null
  errorCategory?: PowerShellStderrCategory | null
}

type AvailabilityProbeResult = {
  ok: boolean
  errorCode: string | null
}

interface PowerShellExecutionResult {
  stdout: Buffer
  stderr: Buffer
  exitCode: number | null
  timedOut: boolean
  spawnSucceeded: boolean
  stdoutJsonFound: boolean
  stdoutJson: unknown | null
  stderrCategory: PowerShellStderrCategory
  failureStep: TaskVerificationFailureStep
  tempFileCreated: boolean
  scriptCleanupSucceeded: boolean
  payloadCleanupSucceeded: boolean
  tempFileCleanupSucceeded: boolean
  stderrFullyQualifiedErrorId: string | null
  stderrLineNumber: number | null
  stderrColumnNumber: number | null
  stderrSha256: string | null
}

type PowerShellExecutionError = Error & Partial<PowerShellExecutionResult> & {
  code?: string | number
  diagnosticCode?: string
}

interface WindowsPasteVerifierOptions {
  execPowerShell?: (payload: Record<string, unknown>) => Promise<RawVerifierPayload>
  runAvailabilityProbe?: () => Promise<AvailabilityProbeResult>
  probeTtlMs?: number
  providerInstanceId?: string
}

const UTF8_POWERSHELL_PREAMBLE = `
$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
`

const PRECHECK_SCRIPT = `
${UTF8_POWERSHELL_PREAMBLE}
try {
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  [Console]::WriteLine(([PSCustomObject]@{
    ok = ($null -ne $root)
    errorCode = $(if ($null -ne $root) { $null } else { "${UIA_DIAGNOSTIC_CODES.rootUnavailable}" })
  } | ConvertTo-Json -Compress))
} catch {
  [Console]::WriteLine(([PSCustomObject]@{
    ok = $false
    errorCode = 'UIA_TASK_SCRIPT_FAILED'
    failureStep = 'POWERSHELL_SCRIPT_RUNTIME'
    errorCategory = 'POWERSHELL_RUNTIME_EXCEPTION'
  } | ConvertTo-Json -Compress))
  exit 1
}
`

const MAIN_SCRIPT = `
${UTF8_POWERSHELL_PREAMBLE}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class LangBotUser32 {
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();

  [DllImport("user32.dll", SetLastError = true)]
  public static extern IntPtr GetWindow(IntPtr hWnd, uint uCmd);

  [DllImport("user32.dll", SetLastError = true)]
  public static extern IntPtr GetAncestor(IntPtr hWnd, uint gaFlags);

  [DllImport("user32.dll", SetLastError = true)]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

  [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder lpClassName, int nMaxCount);

  [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
}
"@

function Get-WindowClassNameValue([System.IntPtr]$handle) {
  if ($handle -eq [System.IntPtr]::Zero) {
    return $null
  }

  $builder = New-Object System.Text.StringBuilder 256
  [void][LangBotUser32]::GetClassName($handle, $builder, $builder.Capacity)
  $value = [string]$builder.ToString()
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $null
  }
  return $value
}

function Get-WindowTitleValue([System.IntPtr]$handle) {
  if ($handle -eq [System.IntPtr]::Zero) {
    return $null
  }

  $builder = New-Object System.Text.StringBuilder 1024
  [void][LangBotUser32]::GetWindowText($handle, $builder, $builder.Capacity)
  $value = [string]$builder.ToString()
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $null
  }
  return $value
}

function Get-ElementText([System.Windows.Automation.AutomationElement]$element) {
  $values = New-Object System.Collections.Generic.List[string]
  if ($null -eq $element) {
    return @()
  }

  try {
    $name = [string]$element.Current.Name
    if (-not [string]::IsNullOrWhiteSpace($name)) {
      [void]$values.Add($name)
    }
  } catch {}

  try {
    $valuePatternObject = $element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    if ($null -ne $valuePatternObject) {
      $valuePattern = [System.Windows.Automation.ValuePattern]$valuePatternObject
      $value = [string]$valuePattern.Current.Value
      if (-not [string]::IsNullOrWhiteSpace($value)) {
        [void]$values.Add($value)
      }
    }
  } catch {}

  try {
    $textPatternObject = $element.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    if ($null -ne $textPatternObject) {
      $textPattern = [System.Windows.Automation.TextPattern]$textPatternObject
      $textValue = [string]$textPattern.DocumentRange.GetText(-1)
      if (-not [string]::IsNullOrWhiteSpace($textValue)) {
        [void]$values.Add($textValue)
      }
    }
  } catch {}

  return @($values | Where-Object { $_ -and $_.Trim().Length -gt 0 } | Select-Object -Unique)
}

function Get-EditableTexts([System.Windows.Automation.AutomationElement]$root) {
  $results = New-Object System.Collections.Generic.List[object]
  if ($null -eq $root) {
    return ,$results.ToArray()
  }

  $controls = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition
  )

  foreach ($control in $controls) {
    try {
      if ($control.Current.IsOffscreen) {
        continue
      }
    } catch {}

    $controlType = $null
    try {
      $controlType = $control.Current.ControlType
    } catch {}

    if (
      $controlType -ne [System.Windows.Automation.ControlType]::Edit -and
      $controlType -ne [System.Windows.Automation.ControlType]::Document
    ) {
      continue
    }

    $texts = Get-ElementText $control
    $hasAnyText = $texts.Count -gt 0
    if (-not $hasAnyText) {
      try {
        if (-not $control.Current.IsKeyboardFocusable) {
          continue
        }
      } catch {
        continue
      }
    }

    foreach ($text in $texts) {
      [void]$results.Add([PSCustomObject]@{
        text = [string]$text
        controlType = [string]$controlType.ProgrammaticName
      })
    }

    if (-not $hasAnyText) {
      [void]$results.Add([PSCustomObject]@{
        text = ''
        controlType = [string]$controlType.ProgrammaticName
      })
    }
  }

  return ,$results.ToArray()
}

function Get-ConversationCandidates([System.Windows.Automation.AutomationElement]$root) {
  $results = New-Object System.Collections.Generic.List[string]
  if ($null -eq $root) {
    return @()
  }

  $controls = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition
  )

  foreach ($control in $controls) {
    $controlType = $null
    try {
      $controlType = $control.Current.ControlType
    } catch {}
    if ($controlType -ne [System.Windows.Automation.ControlType]::Text -and $controlType -ne [System.Windows.Automation.ControlType]::Document) {
      continue
    }
    foreach ($text in Get-ElementText $control) {
      if ($text.Trim().Length -gt 0 -and $text.Length -le 200) {
        [void]$results.Add([string]$text)
      }
    }
  }

  return @($results)
}

try {
  $payload = ConvertFrom-Json ([Environment]::GetEnvironmentVariable('LANGBOT_PASTE_VERIFIER_REQUEST'))
  $foreground = [LangBotUser32]::GetForegroundWindow()
  $owner = [LangBotUser32]::GetWindow($foreground, 4)
  $rootOwner = [LangBotUser32]::GetAncestor($foreground, 3)
  if ($rootOwner -eq [System.IntPtr]::Zero) {
    $rootOwner = $foreground
  }
  $processId = 0
  [void][LangBotUser32]::GetWindowThreadProcessId($foreground, [ref]$processId)
  $processPath = $null
  try {
    $processPath = (Get-Process -Id $processId -ErrorAction Stop).Path
  } catch {
    $processPath = $null
  }

  $windowHandleInt = [int][Int64]$rootOwner
  $root = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
    [System.Windows.Automation.TreeScope]::Children,
    (New-Object System.Windows.Automation.PropertyCondition(
      [System.Windows.Automation.AutomationElement]::NativeWindowHandleProperty,
      $windowHandleInt
    ))
  )

  $conversationCandidates = Get-ConversationCandidates $root
  $editableTexts = Get-EditableTexts $root
  $actualText = $null
  if ($editableTexts.Count -gt 0) {
    $nonEmptyEditable = @($editableTexts | Where-Object { $_.text -and $_.text.Trim().Length -gt 0 })
    if ($nonEmptyEditable.Count -gt 0) {
      $actualText = ($nonEmptyEditable | Sort-Object { $_.text.Length } -Descending | Select-Object -First 1).text
    } else {
      $actualText = ''
    }
  }

  [Console]::WriteLine(([PSCustomObject]@{
    activeWindowHandle = [string]([Int64]$foreground)
    activeOwnerWindowHandle = [string]([Int64]$owner)
    activeRootOwnerWindowHandle = [string]([Int64]$rootOwner)
    activeProcessId = [int]$processId
    activeExecutablePath = $processPath
    activeWindowTitle = Get-WindowTitleValue $foreground
    activeWindowClassName = Get-WindowClassNameValue $foreground
    activeRootOwnerWindowTitle = Get-WindowTitleValue $rootOwner
    activeRootOwnerWindowClassName = Get-WindowClassNameValue $rootOwner
    conversationCandidates = @($conversationCandidates)
    inputLocated = [bool]($editableTexts.Count -gt 0)
    actualText = $actualText
  } | ConvertTo-Json -Depth 6 -Compress))
} catch {
  [Console]::WriteLine(([PSCustomObject]@{
    ok = $false
    errorCode = 'UIA_TASK_SCRIPT_FAILED'
    failureStep = 'POWERSHELL_SCRIPT_RUNTIME'
    errorCategory = 'POWERSHELL_RUNTIME_EXCEPTION'
  } | ConvertTo-Json -Compress))
  exit 1
}
`

function normalizeExecutablePath(value: string | null | undefined): string {
  return String(value ?? '').trim().replace(/\\/g, '/').toLowerCase()
}

function normalizeHandle(value: string | number | null | undefined): string {
  const normalized = String(value ?? '').trim()
  return normalized.length > 0 ? normalized : '0'
}

function normalizeWindowClassName(value: string | null | undefined): string {
  return String(value ?? '').trim().toLowerCase()
}

function expectedRootOwnerHandle(window: PasteVerificationArgs['window']): string {
  return normalizeHandle(window.rootWindowId ?? window.ownerWindowId ?? window.windowId)
}

function actualRootOwnerHandle(raw: RawVerifierPayload): string {
  return normalizeHandle(raw.activeRootOwnerWindowHandle ?? raw.activeOwnerWindowHandle ?? raw.activeWindowHandle)
}

function expectedTrustedClass(window: PasteVerificationArgs['window']): string {
  return normalizeWindowClassName(window.className)
}

function actualTrustedClass(raw: RawVerifierPayload): string {
  return normalizeWindowClassName(raw.activeRootOwnerWindowClassName ?? raw.activeWindowClassName)
}

function matchesTrustedWindowIdentity(args: PasteVerificationArgs, raw: RawVerifierPayload): boolean {
  return actualRootOwnerHandle(raw) === expectedRootOwnerHandle(args.window)
    && Number(raw.activeProcessId ?? 0) === Number(args.window.processId)
    && normalizeExecutablePath(raw.activeExecutablePath) === normalizeExecutablePath(args.window.executablePath)
    && (
      expectedTrustedClass(args.window).length === 0
      || actualTrustedClass(raw).length === 0
      || actualTrustedClass(raw) === expectedTrustedClass(args.window)
    )
}

function normalizeNewlines(text: string): string {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
}

function measureText(text: string) {
  const normalized = normalizeNewlines(text)
  const crMatches = text.match(/\r/g)
  const lfMatches = text.match(/\n/g)
  return {
    textLengthUtf16: text.length,
    codePointCount: [...text].length,
    digest: createHash('sha256').update(text, 'utf8').digest('hex'),
    lineCount: normalized.length === 0 ? 1 : normalized.split('\n').length,
    crCount: crMatches?.length ?? 0,
    lfCount: lfMatches?.length ?? 0,
  }
}

function decodeProcessBuffer(value: string | Buffer | null | undefined): string {
  if (Buffer.isBuffer(value)) {
    return value.toString('utf8')
  }
  return String(value ?? '')
}

function normalizeStdoutText(value: string | Buffer | null | undefined): string {
  return decodeProcessBuffer(value).replace(/^\uFEFF/, '').trim()
}

function parseJsonStdoutPayload<T>(stdout: Buffer | string | null | undefined): { found: boolean; payload: T | null } {
  const decoded = normalizeStdoutText(stdout)
  if (!decoded) {
    return { found: false, payload: null }
  }
  try {
    return { found: true, payload: JSON.parse(decoded) as T }
  } catch {
    return { found: false, payload: null }
  }
}

function parseJsonStdout<T>(stdout: Buffer | string | null | undefined): T {
  const parsed = parseJsonStdoutPayload<T>(stdout)
  if (parsed.found && parsed.payload !== null) {
    return parsed.payload
  }
  const error = new Error('Invalid PowerShell JSON stdout') as PowerShellExecutionError
  error.diagnosticCode = UIA_DIAGNOSTIC_CODES.outputInvalid
  throw error
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function rmWithRetry(targetPath: string): Promise<boolean> {
  for (let attempt = 0; attempt <= CLEANUP_RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      await fs.rm(targetPath, { recursive: true, force: true })
      return true
    } catch {
      if (attempt >= CLEANUP_RETRY_DELAYS_MS.length) {
        return false
      }
      await delay(CLEANUP_RETRY_DELAYS_MS[attempt]!)
    }
  }
  return false
}

function detectStderrCategory(stderr: Buffer | string | null | undefined): {
  category: PowerShellStderrCategory
  fullyQualifiedErrorId: string | null
  lineNumber: number | null
  columnNumber: number | null
  sha256: string | null
} {
  const text = decodeProcessBuffer(stderr)
  const sha256 = text ? createHash('sha256').update(text, 'utf8').digest('hex') : null
  const fullyQualifiedErrorId = text.match(/FullyQualifiedErrorId\s*:\s*([^\r\n]+)/i)?.[1]?.trim() ?? null
  const lineMatch = text.match(/At line:(\d+) char:(\d+)/i)
  let category: PowerShellStderrCategory = 'none'

  if (/ParserError|Unexpected token|Missing .* terminator|ExpectedExpression/i.test(text)) {
    category = 'POWERSHELL_PARSE_ERROR'
  } else if (/ParameterBinding|NamedParameterNotFound|PositionalParameterNotFound|Cannot bind parameter/i.test(text)) {
    category = 'POWERSHELL_PARAMETER_BINDING_ERROR'
  } else if (/Add-Type|Cannot find type|Unable to find type|Could not load file or assembly/i.test(text)) {
    category = 'POWERSHELL_TYPE_LOAD_ERROR'
  } else if (/CommandNotFoundException|is not recognized as the name of a cmdlet|The term .* is not recognized/i.test(text)) {
    category = 'POWERSHELL_COMMAND_NOT_FOUND'
  } else if (/Access is denied|UnauthorizedAccessException|PermissionDenied/i.test(text)) {
    category = 'POWERSHELL_ACCESS_DENIED'
  } else if (text.trim().length > 0) {
    category = 'POWERSHELL_RUNTIME_EXCEPTION'
  }

  if (text.trim().length > 0 && category === 'none') {
    category = 'POWERSHELL_UNKNOWN_ERROR'
  }

  return {
    category,
    fullyQualifiedErrorId,
    lineNumber: lineMatch?.[1] ? Number(lineMatch[1]) : null,
    columnNumber: lineMatch?.[2] ? Number(lineMatch[2]) : null,
    sha256,
  }
}

function mapCategoryToFailureStep(
  category: PowerShellStderrCategory,
  timedOut: boolean,
  stdoutJsonFound: boolean,
): TaskVerificationFailureStep {
  if (timedOut) {
    return 'POWERSHELL_TIMEOUT'
  }
  if (category === 'POWERSHELL_PARSE_ERROR' || category === 'POWERSHELL_PARAMETER_BINDING_ERROR') {
    return 'POWERSHELL_SCRIPT_PARSE'
  }
  if (category === 'POWERSHELL_RUNTIME_EXCEPTION' || category === 'POWERSHELL_TYPE_LOAD_ERROR' || category === 'POWERSHELL_ACCESS_DENIED') {
    return 'POWERSHELL_SCRIPT_RUNTIME'
  }
  if (stdoutJsonFound) {
    return 'POWERSHELL_OUTPUT_PARSE'
  }
  return 'OUTPUT_PARSE'
}

function unavailableDiagnosticCode(error?: unknown): string {
  const executionError = error as PowerShellExecutionError
  if (typeof executionError.diagnosticCode === 'string') {
    return executionError.diagnosticCode
  }
  if (executionError.stderrCategory === 'POWERSHELL_COMMAND_NOT_FOUND') {
    return UIA_DIAGNOSTIC_CODES.powershellNotFound
  }
  if (executionError.stderrCategory === 'POWERSHELL_TYPE_LOAD_ERROR') {
    return UIA_DIAGNOSTIC_CODES.assemblyLoadFailed
  }
  if (executionError.timedOut) {
    return UIA_DIAGNOSTIC_CODES.probeTimeout
  }
  return UIA_DIAGNOSTIC_CODES.probeFailed
}

function getStructuredScriptError(error: unknown): ScriptErrorPayload | null {
  const executionError = error as PowerShellExecutionError
  if (executionError.stdoutJson && typeof executionError.stdoutJson === 'object') {
    return executionError.stdoutJson as ScriptErrorPayload
  }
  const parsed = parseJsonStdoutPayload<ScriptErrorPayload>(executionError.stdout)
  return parsed.found ? parsed.payload : null
}

async function execPowerShellCommand(
  script: string,
  payload?: Record<string, unknown>,
): Promise<PowerShellExecutionResult> {
  const env = {
    ...process.env,
    LANGBOT_PASTE_VERIFIER_REQUEST: payload ? JSON.stringify(payload) : '',
  }
  const scriptDirectory = await fs.mkdtemp(path.join(tmpdir(), 'langbot-paste-verifier-'))
  const scriptPath = path.join(scriptDirectory, 'probe.ps1')
  const payloadPath = path.join(scriptDirectory, 'payload.json')
  let tempFileCreated = false
  let successResult: Omit<PowerShellExecutionResult, 'scriptCleanupSucceeded' | 'payloadCleanupSucceeded' | 'tempFileCleanupSucceeded'> | null = null
  let failure: PowerShellExecutionError | null = null

  try {
    await fs.writeFile(scriptPath, `\uFEFF${script}`, 'utf8')
    await fs.writeFile(payloadPath, payload ? JSON.stringify(payload) : '', 'utf8')
    tempFileCreated = true
    const result = await execFileAsync(
      'powershell.exe',
      [
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy', 'Bypass',
        '-STA',
        '-File', scriptPath,
      ],
      {
        encoding: 'buffer',
        env,
        windowsHide: true,
        maxBuffer: 1024 * 1024,
        timeout: DEFAULT_COMMAND_TIMEOUT_MS,
        killSignal: 'SIGKILL',
      },
    )
    const stderrDetails = detectStderrCategory(result.stderr)
    const stdoutJson = parseJsonStdoutPayload(result.stdout)
    successResult = {
      stdout: Buffer.isBuffer(result.stdout) ? result.stdout : Buffer.from(result.stdout ?? ''),
      stderr: Buffer.isBuffer(result.stderr) ? result.stderr : Buffer.from(result.stderr ?? ''),
      exitCode: 0,
      timedOut: false,
      spawnSucceeded: true,
      stdoutJsonFound: stdoutJson.found,
      stdoutJson: stdoutJson.payload,
      stderrCategory: stderrDetails.category,
      failureStep: 'OUTPUT_PARSE',
      tempFileCreated,
      stderrFullyQualifiedErrorId: stderrDetails.fullyQualifiedErrorId,
      stderrLineNumber: stderrDetails.lineNumber,
      stderrColumnNumber: stderrDetails.columnNumber,
      stderrSha256: stderrDetails.sha256,
    }
  } catch (rawError) {
    const error = rawError as NodeJS.ErrnoException & {
      stdout?: Buffer | string
      stderr?: Buffer | string
      code?: string | number
      killed?: boolean
      signal?: NodeJS.Signals | null
    }
    const stdout = Buffer.isBuffer(error.stdout) ? error.stdout : Buffer.from(error.stdout ?? '')
    const stderr = Buffer.isBuffer(error.stderr) ? error.stderr : Buffer.from(error.stderr ?? '')
    const stdoutJson = parseJsonStdoutPayload<ScriptErrorPayload>(stdout)
    const timedOut = Boolean(error.killed || error.signal === 'SIGKILL')
    const startupCode = typeof error.code === 'string' ? error.code : null
    const spawnSucceeded = !(startupCode && STARTUP_ERROR_CODES.has(startupCode))
    const stderrDetails = detectStderrCategory(stderr)
    const stderrCategory: PowerShellStderrCategory =
      startupCode === 'ENOENT'
        ? 'POWERSHELL_COMMAND_NOT_FOUND'
        : stderrDetails.category === 'none' && !timedOut && !stdoutJson.found
          ? 'POWERSHELL_UNKNOWN_ERROR'
          : stderrDetails.category
    const failureStep = stdoutJson.payload?.failureStep
      ?? (spawnSucceeded
        ? mapCategoryToFailureStep(stderrCategory, timedOut, stdoutJson.found)
        : 'TASK_SCRIPT_SPAWN')
    const wrapped = new Error('PowerShell execution failed') as PowerShellExecutionError
    wrapped.stdout = stdout
    wrapped.stderr = stderr
    wrapped.exitCode = typeof error.code === 'number' ? error.code : null
    wrapped.timedOut = timedOut
    wrapped.spawnSucceeded = spawnSucceeded
    wrapped.stdoutJsonFound = stdoutJson.found
    wrapped.stdoutJson = stdoutJson.payload
    wrapped.stderrCategory = stderrCategory
    wrapped.failureStep = failureStep
    wrapped.tempFileCreated = tempFileCreated
    wrapped.stderrFullyQualifiedErrorId = stderrDetails.fullyQualifiedErrorId
    wrapped.stderrLineNumber = stderrDetails.lineNumber
    wrapped.stderrColumnNumber = stderrDetails.columnNumber
    wrapped.stderrSha256 = stderrDetails.sha256
    wrapped.code = error.code
    wrapped.diagnosticCode = stdoutJson.payload?.errorCategory
      ?? (timedOut
        ? UIA_DIAGNOSTIC_CODES.probeTimeout
        : startupCode === 'ENOENT'
          ? UIA_DIAGNOSTIC_CODES.powershellNotFound
          : stderrCategory === 'POWERSHELL_TYPE_LOAD_ERROR'
            ? UIA_DIAGNOSTIC_CODES.assemblyLoadFailed
            : UIA_DIAGNOSTIC_CODES.probeFailed)
    failure = wrapped
  }

  const scriptCleanupSucceeded = await rmWithRetry(scriptPath)
  const payloadCleanupSucceeded = await rmWithRetry(payloadPath)
  await rmWithRetry(scriptDirectory)
  const tempFileCleanupSucceeded = scriptCleanupSucceeded && payloadCleanupSucceeded

  if (failure) {
    failure.scriptCleanupSucceeded = scriptCleanupSucceeded
    failure.payloadCleanupSucceeded = payloadCleanupSucceeded
    failure.tempFileCleanupSucceeded = tempFileCleanupSucceeded
    throw failure
  }

  return {
    ...successResult!,
    scriptCleanupSucceeded,
    payloadCleanupSucceeded,
    tempFileCleanupSucceeded,
  }
}

export async function runPowerShellScript(
  script: string,
  payload?: Record<string, unknown>,
): Promise<RawVerifierPayload> {
  const result = await execPowerShellCommand(script, payload)
  return parseJsonStdout<RawVerifierPayload>(result.stdout)
}

async function runWindowsUiaAvailabilityProbe(): Promise<AvailabilityProbeResult> {
  try {
    const result = await execPowerShellCommand(PRECHECK_SCRIPT)
    const payload = parseJsonStdout<RawAvailabilityPayload>(result.stdout)
    if (payload.ok) {
      return { ok: true, errorCode: null }
    }
    return {
      ok: false,
      errorCode: payload.errorCode ?? UIA_DIAGNOSTIC_CODES.rootUnavailable,
    }
  } catch (error) {
    const stdoutJson = (error as PowerShellExecutionError).stdoutJson as ScriptErrorPayload | null | undefined
    if (stdoutJson?.errorCategory === 'POWERSHELL_TYPE_LOAD_ERROR') {
      return { ok: false, errorCode: UIA_DIAGNOSTIC_CODES.assemblyLoadFailed }
    }
    return {
      ok: false,
      errorCode: unavailableDiagnosticCode(error),
    }
  }
}

function buildCapability(params: {
  available: boolean
  reason: string | null
  diagnosticCode: string | null
  providerInstanceId?: string
}): PasteVerificationCapability {
  return {
    available: params.available,
    reason: params.reason,
    providerInstanceId: params.providerInstanceId,
    diagnosticCode: params.diagnosticCode,
    method: VERIFICATION_METHOD,
    requiresManualConversationOpen: true,
    supportedErrorCodes: [...SUPPORTED_ERROR_CODES],
  }
}

function diagnosticCodeToSanitizedMessage(diagnosticCode: string): string {
  switch (diagnosticCode) {
    case UIA_DIAGNOSTIC_CODES.powershellNotFound:
      return 'PowerShell executable is unavailable for UIA verification'
    case UIA_DIAGNOSTIC_CODES.assemblyLoadFailed:
      return 'UI Automation assemblies could not be loaded'
    case UIA_DIAGNOSTIC_CODES.rootUnavailable:
      return 'UI Automation root element is unavailable'
    case UIA_DIAGNOSTIC_CODES.probeTimeout:
      return 'UI Automation probe timed out'
    case UIA_DIAGNOSTIC_CODES.outputInvalid:
      return 'UI Automation probe returned invalid JSON output'
    default:
      return 'UI Automation probe failed before content verification'
  }
}

function buildUnavailableResult(
  reason: string,
  verificationErrorCode: string,
  diagnosticCode: string,
  diagnosticStage: string,
  providerInstanceId?: string,
  taskVerificationDiagnostic?: TaskVerificationDiagnostic,
): PasteInputObservationResult {
  return {
    ok: false,
    inputLocated: false,
    draftWritten: false,
    contentVerified: false,
    providerInstanceId,
    observationAvailable: false,
    runtimeState: 'paste_verification_unavailable',
    errorCode: reason || PASTE_VERIFICATION_UNAVAILABLE,
    verificationMethod: VERIFICATION_METHOD,
    verificationErrorCode,
    diagnosticCode,
    diagnosticStage,
    sanitizedMessage: diagnosticCodeToSanitizedMessage(diagnosticCode),
    taskVerificationDiagnostic,
  }
}

function taskScriptErrorToDiagnostic(
  error: unknown,
  phase: 'before_paste' | 'after_paste' | 'after_send',
): TaskVerificationDiagnostic {
  const executionError = error as PowerShellExecutionError
  return {
    scriptKind: phase === 'before_paste' ? 'input_inspection' : 'content_read',
    spawnSucceeded: Boolean(executionError.spawnSucceeded),
    timedOut: Boolean(executionError.timedOut),
    exitCode: typeof executionError.exitCode === 'number' ? Number(executionError.exitCode) : null,
    stdoutJsonFound: Boolean(executionError.stdoutJsonFound),
    stderrCategory: executionError.stderrCategory ?? 'POWERSHELL_UNKNOWN_ERROR',
    tempFileCreated: Boolean(executionError.tempFileCreated),
    scriptCleanupSucceeded: typeof executionError.scriptCleanupSucceeded === 'boolean'
      ? executionError.scriptCleanupSucceeded
      : undefined,
    payloadCleanupSucceeded: typeof executionError.payloadCleanupSucceeded === 'boolean'
      ? executionError.payloadCleanupSucceeded
      : undefined,
    tempFileCleanupSucceeded: Boolean(executionError.tempFileCleanupSucceeded),
    failureStep: executionError.failureStep ?? 'TASK_SCRIPT_SPAWN',
    stderrFullyQualifiedErrorId: executionError.stderrFullyQualifiedErrorId ?? null,
    stderrLineNumber: executionError.stderrLineNumber ?? null,
    stderrColumnNumber: executionError.stderrColumnNumber ?? null,
    stderrSha256: executionError.stderrSha256 ?? null,
    windowFound: false,
    conversationObserved: false,
    conversationMatched: false,
    inputElementFound: false,
    valuePatternAvailable: false,
    textPatternAvailable: false,
    textObserved: false,
  }
}

export function createWindowsPasteVerificationProvider(
  options: WindowsPasteVerifierOptions = {},
): PasteVerificationProvider {
  const providerInstanceId = String(options.providerInstanceId ?? 'windows-paste-verifier')
  const execPowerShell =
    options.execPowerShell ??
    (async (payload: Record<string, unknown>) => runPowerShellScript(MAIN_SCRIPT, payload))
  const runAvailabilityProbe = options.runAvailabilityProbe ?? runWindowsUiaAvailabilityProbe
  const probeTtlMs = Math.max(0, options.probeTtlMs ?? DEFAULT_PROBE_TTL_MS)

  let capability = buildCapability({
    available: process.platform === 'win32',
    reason: process.platform === 'win32' ? null : PASTE_VERIFICATION_UNAVAILABLE,
    diagnosticCode: process.platform === 'win32' ? null : UIA_DIAGNOSTIC_CODES.probeFailed,
    providerInstanceId,
  })
  let lastProbeAt = 0
  let capabilityProbeCount = 0
  let capabilityProbeSpawnCount = 0
  let capabilityExpiresAt = 0
  let lastCapabilityDiagnosticCode: string | null = capability.diagnosticCode ?? null
  let capabilityProbeDiagnostic: PasteVerificationCapability['capabilityProbeDiagnostic'] = null
  let pendingProbe: Promise<PasteVerificationCapability> | null = null

  const enrichCapability = (base: PasteVerificationCapability, now = Date.now()): PasteVerificationCapability => ({
    ...base,
    capabilityCheckedAt: lastProbeAt > 0 ? new Date(lastProbeAt).toISOString() : null,
    capabilityExpiresAt: capabilityExpiresAt > 0 ? new Date(capabilityExpiresAt).toISOString() : null,
    capabilityAgeMs: lastProbeAt > 0 ? Math.max(0, now - lastProbeAt) : null,
    capabilityProbeCount,
    capabilityProbeSpawnCount,
    lastCapabilityDiagnosticCode,
    capabilityProbeDiagnostic,
  })

  const refreshCapability = async (force = true): Promise<PasteVerificationCapability> => {
    if (process.platform !== 'win32') {
      capability = enrichCapability(buildCapability({
        available: false,
        reason: PASTE_VERIFICATION_UNAVAILABLE,
        diagnosticCode: UIA_DIAGNOSTIC_CODES.probeFailed,
        providerInstanceId,
      }))
      return capability
    }

    const now = Date.now()
    if (!force && lastProbeAt > 0 && now - lastProbeAt < probeTtlMs) {
      return enrichCapability(capability, now)
    }
    if (!force && pendingProbe) {
      return pendingProbe
    }

    pendingProbe = (async () => {
      capabilityProbeCount += 1
      capabilityProbeSpawnCount += 1
      const probeResult = await runAvailabilityProbe()
      const checkedAt = Date.now()
      lastProbeAt = checkedAt
      capabilityExpiresAt = checkedAt + probeTtlMs
      lastCapabilityDiagnosticCode = probeResult.errorCode ?? null
      capabilityProbeDiagnostic = {
        scriptKind: 'availability_probe',
        spawnSucceeded: true,
        timedOut: probeResult.errorCode === UIA_DIAGNOSTIC_CODES.probeTimeout,
        exitCode: probeResult.ok ? 0 : null,
        stdoutJsonFound: true,
        stderrCategory: probeResult.errorCode === UIA_DIAGNOSTIC_CODES.assemblyLoadFailed
          ? 'POWERSHELL_TYPE_LOAD_ERROR'
          : probeResult.errorCode === UIA_DIAGNOSTIC_CODES.powershellNotFound
            ? 'POWERSHELL_COMMAND_NOT_FOUND'
            : probeResult.ok
              ? 'none'
              : 'POWERSHELL_UNKNOWN_ERROR',
        tempFileCreated: true,
        scriptCleanupSucceeded: true,
        payloadCleanupSucceeded: true,
        tempFileCleanupSucceeded: true,
        failureStep: probeResult.ok
          ? 'OUTPUT_PARSE'
          : probeResult.errorCode === UIA_DIAGNOSTIC_CODES.powershellNotFound
            ? 'TASK_SCRIPT_SPAWN'
            : probeResult.errorCode === UIA_DIAGNOSTIC_CODES.probeTimeout
              ? 'POWERSHELL_TIMEOUT'
              : 'POWERSHELL_SCRIPT_RUNTIME',
        stderrFullyQualifiedErrorId: null,
        stderrLineNumber: null,
        stderrColumnNumber: null,
        stderrSha256: null,
      }
      capability = probeResult.ok
        ? buildCapability({
            available: true,
            reason: null,
            diagnosticCode: null,
            providerInstanceId,
          })
        : buildCapability({
            available: false,
            reason: PASTE_VERIFICATION_UNAVAILABLE,
            diagnosticCode: probeResult.errorCode ?? UIA_DIAGNOSTIC_CODES.probeFailed,
            providerInstanceId,
          })
      capability = enrichCapability(capability, checkedAt)
      return capability
    })()

    try {
      return await pendingProbe
    } finally {
      pendingProbe = null
    }
  }

  if (!options.runAvailabilityProbe) {
    void refreshCapability(true)
  }

  const verifyInputContent = async (args: PasteVerificationArgs) => {
    const maxAttempts = args.phase === 'before_paste'
      ? WINDOW_STABILIZATION_RETRY_DELAYS_MS.length + 1
      : 1

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      let raw: RawVerifierPayload
      try {
        raw = await execPowerShell({
          conversationName: args.conversationName,
          draftText: args.draftText,
          expectedWindowId: String(args.window.windowId),
          expectedRootOwnerWindowId: expectedRootOwnerHandle(args.window),
          expectedProcessId: Number(args.window.processId),
          expectedExecutablePath: normalizeExecutablePath(args.window.executablePath),
          expectedWindowClassName: expectedTrustedClass(args.window),
          phase: args.phase,
        })
      } catch (error) {
        const executionError = error as PowerShellExecutionError
        const stdoutJson = getStructuredScriptError(error)
        const diagnosticCode = stdoutJson?.errorCategory ?? unavailableDiagnosticCode(error)
        const verificationErrorCode = stdoutJson?.errorCode ?? diagnosticCode
        const taskDiagnostic = taskScriptErrorToDiagnostic({
          ...executionError,
          failureStep: stdoutJson?.failureStep ?? executionError.failureStep,
          stderrCategory: stdoutJson?.errorCategory ?? executionError.stderrCategory,
          stdoutJsonFound: stdoutJson ? true : executionError.stdoutJsonFound,
        }, args.phase)
        return buildUnavailableResult(
          'UIA_TASK_SCRIPT_FAILED',
          verificationErrorCode,
          diagnosticCode,
          args.phase === 'before_paste'
            ? 'before_paste_verification'
            : args.phase === 'after_send'
              ? 'after_send_verification'
              : 'after_paste_verification',
          providerInstanceId,
          taskDiagnostic,
        )
      }

      if (!matchesTrustedWindowIdentity(args, raw)) {
        return {
          ok: false,
          inputLocated: false,
          draftWritten: false,
          contentVerified: false,
          providerInstanceId,
          observationAvailable: false,
          runtimeState: 'target_window_changed',
          errorCode: 'TARGET_WINDOW_CHANGED',
          verificationMethod: VERIFICATION_METHOD,
          verificationErrorCode: 'TARGET_WINDOW_CHANGED',
        }
      }

      if (!raw.inputLocated) {
        if (args.phase === 'before_paste' && attempt < maxAttempts - 1) {
          await delay(WINDOW_STABILIZATION_RETRY_DELAYS_MS[attempt]!)
          continue
        }
        return {
          ok: false,
          inputLocated: false,
          draftWritten: false,
          contentVerified: false,
          providerInstanceId,
          observationAvailable: false,
          runtimeState: 'input_not_located',
          errorCode: 'INPUT_NOT_LOCATED',
          verificationMethod: VERIFICATION_METHOD,
          verificationErrorCode: 'INPUT_NOT_LOCATED',
        }
      }

      if (args.phase === 'before_paste') {
        return {
          ok: true,
          inputLocated: true,
          draftWritten: false,
          contentVerified: false,
          conversationCandidates: Array.isArray(raw.conversationCandidates)
            ? raw.conversationCandidates
              .filter((candidate): candidate is string => typeof candidate === 'string')
            : [],
          observedConversation: raw.activeRootOwnerWindowTitle ?? raw.activeWindowTitle ?? null,
          providerInstanceId,
          observationAvailable: false,
          verificationMethod: VERIFICATION_METHOD,
        }
      }

      const actualText = typeof raw.actualText === 'string' ? raw.actualText : ''
      const expectedDiagnostics = measureText(args.draftText)
      const actualDiagnostics = measureText(actualText)
      if (args.phase === 'after_send') {
        const inputCleared = actualText.length === 0
        if (!inputCleared) {
          return {
            ok: false,
            inputLocated: true,
            draftWritten: true,
            contentVerified: false,
            providerInstanceId,
            observationAvailable: true,
            runtimeState: 'post_send_input_not_cleared',
            errorCode: 'POST_SEND_INPUT_NOT_CLEARED',
            verificationMethod: VERIFICATION_METHOD,
            verificationErrorCode: 'POST_SEND_INPUT_NOT_CLEARED',
            actualTextLength: actualDiagnostics.textLengthUtf16,
            actualCodePointCount: actualDiagnostics.codePointCount,
            actualDigest: actualDiagnostics.digest,
            actualLineCount: actualDiagnostics.lineCount,
            actualCrCount: actualDiagnostics.crCount,
            actualLfCount: actualDiagnostics.lfCount,
          }
        }
        return {
          ok: true,
          inputLocated: true,
          draftWritten: false,
          contentVerified: true,
          conversationCandidates: Array.isArray(raw.conversationCandidates)
            ? raw.conversationCandidates
              .filter((candidate): candidate is string => typeof candidate === 'string')
            : [],
          observedConversation: raw.activeRootOwnerWindowTitle ?? raw.activeWindowTitle ?? null,
          providerInstanceId,
          observationAvailable: true,
          runtimeState: 'post_send_input_cleared',
          verificationMethod: VERIFICATION_METHOD,
          actualTextLength: actualDiagnostics.textLengthUtf16,
          actualCodePointCount: actualDiagnostics.codePointCount,
          actualDigest: actualDiagnostics.digest,
          actualLineCount: actualDiagnostics.lineCount,
          actualCrCount: actualDiagnostics.crCount,
          actualLfCount: actualDiagnostics.lfCount,
        }
      }

      const contentVerified =
        expectedDiagnostics.textLengthUtf16 === actualDiagnostics.textLengthUtf16
        && expectedDiagnostics.codePointCount === actualDiagnostics.codePointCount
        && expectedDiagnostics.digest === actualDiagnostics.digest
        && expectedDiagnostics.lineCount === actualDiagnostics.lineCount

      if (!contentVerified) {
        return {
          ok: false,
          inputLocated: true,
          draftWritten: actualText.length > 0,
          contentVerified: false,
          providerInstanceId,
          observationAvailable: true,
          runtimeState: 'paste_content_mismatch',
          errorCode: 'PASTE_CONTENT_MISMATCH',
          verificationMethod: VERIFICATION_METHOD,
          verificationErrorCode: 'PASTE_CONTENT_MISMATCH',
          actualTextLength: actualDiagnostics.textLengthUtf16,
          actualCodePointCount: actualDiagnostics.codePointCount,
          actualDigest: actualDiagnostics.digest,
          actualLineCount: actualDiagnostics.lineCount,
          actualCrCount: actualDiagnostics.crCount,
          actualLfCount: actualDiagnostics.lfCount,
        }
      }

      return {
        ok: true,
        inputLocated: true,
        draftWritten: true,
        contentVerified: true,
        conversationCandidates: Array.isArray(raw.conversationCandidates)
          ? raw.conversationCandidates
            .filter((candidate): candidate is string => typeof candidate === 'string')
          : [],
        observedConversation: raw.activeRootOwnerWindowTitle ?? raw.activeWindowTitle ?? null,
        providerInstanceId,
        observationAvailable: true,
        verificationMethod: VERIFICATION_METHOD,
        actualTextLength: actualDiagnostics.textLengthUtf16,
        actualCodePointCount: actualDiagnostics.codePointCount,
        actualDigest: actualDiagnostics.digest,
        actualLineCount: actualDiagnostics.lineCount,
        actualCrCount: actualDiagnostics.crCount,
        actualLfCount: actualDiagnostics.lfCount,
      }
    }

    return {
      ok: false,
      inputLocated: false,
      draftWritten: false,
      contentVerified: false,
      providerInstanceId,
      observationAvailable: false,
      runtimeState: 'input_not_located',
      errorCode: 'INPUT_NOT_LOCATED',
      verificationMethod: VERIFICATION_METHOD,
      verificationErrorCode: 'INPUT_NOT_LOCATED',
    }
  }

  return {
    getCapability: () => enrichCapability(capability),
    getCachedCapability: () => enrichCapability(capability),
    refreshCapability,
    verifyInputContent,
    verifyPasteContent: async (args: PasteVerificationArgs) => verifyInputContent(args),
  }
}
