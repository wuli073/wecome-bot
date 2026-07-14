import type { WindowDescriptor } from '../domain/window-types'

export type PasteVerificationPhase = 'before_paste' | 'after_paste' | 'after_send'

export interface PasteVerificationArgs {
  conversationName: string
  draftText: string
  window: WindowDescriptor
  phase: PasteVerificationPhase
}

export type PowerShellStderrCategory =
  | 'none'
  | 'POWERSHELL_PARSE_ERROR'
  | 'POWERSHELL_PARAMETER_BINDING_ERROR'
  | 'POWERSHELL_TYPE_LOAD_ERROR'
  | 'POWERSHELL_COMMAND_NOT_FOUND'
  | 'POWERSHELL_RUNTIME_EXCEPTION'
  | 'POWERSHELL_ACCESS_DENIED'
  | 'POWERSHELL_UNKNOWN_ERROR'

export type TaskVerificationFailureStep =
  | 'TASK_SCRIPT_SPAWN'
  | 'UIA_ASSEMBLY_LOAD'
  | 'UIA_ROOT_ACCESS'
  | 'TARGET_WINDOW_LOOKUP'
  | 'FOREGROUND_WINDOW_CHECK'
  | 'CONVERSATION_LOOKUP'
  | 'CONVERSATION_MISMATCH'
  | 'INPUT_LOOKUP'
  | 'INPUT_PATTERN_UNAVAILABLE'
  | 'INPUT_TEXT_READ'
  | 'OUTPUT_PARSE'
  | 'TASK_SCRIPT_TIMEOUT'
  | 'POWERSHELL_SCRIPT_PARSE'
  | 'POWERSHELL_SCRIPT_RUNTIME'
  | 'POWERSHELL_OUTPUT_PARSE'
  | 'POWERSHELL_TIMEOUT'

export interface PasteInputObservationResult {
  ok: boolean
  inputLocated: boolean
  draftWritten: boolean
  contentVerified: boolean
  conversationCandidates?: string[]
  observedConversation?: string | null
  providerInstanceId?: string
  observationAvailable?: boolean
  runtimeState?: string
  errorCode?: string
  verificationMethod?: string
  verificationErrorCode?: string
  diagnosticCode?: string
  diagnosticStage?: string
  sanitizedMessage?: string
  actualTextLength?: number
  actualCodePointCount?: number
  actualDigest?: string
  actualLineCount?: number
  actualCrCount?: number
  actualLfCount?: number
  taskVerificationDiagnostic?: TaskVerificationDiagnostic
}

export interface PasteVerificationResult {
  ok: boolean
  inputLocated: boolean
  draftWritten: boolean
  contentVerified: boolean
  conversationCandidates?: string[]
  observedConversation?: string | null
  providerInstanceId?: string
  observationAvailable?: boolean
  runtimeState?: string
  errorCode?: string
  verificationMethod?: string
  verificationErrorCode?: string
  diagnosticCode?: string
  diagnosticStage?: string
  sanitizedMessage?: string
  actualTextLength?: number
  actualCodePointCount?: number
  actualDigest?: string
  actualLineCount?: number
  actualCrCount?: number
  actualLfCount?: number
  taskVerificationDiagnostic?: TaskVerificationDiagnostic
}

export interface TaskVerificationDiagnostic {
  scriptKind: 'input_inspection' | 'content_read'
  spawnSucceeded: boolean
  timedOut: boolean
  exitCode: number | null
  stdoutJsonFound: boolean
  stderrCategory: PowerShellStderrCategory
  tempFileCreated: boolean
  scriptCleanupSucceeded?: boolean
  payloadCleanupSucceeded?: boolean
  tempFileCleanupSucceeded: boolean
  failureStep: TaskVerificationFailureStep
  stderrFullyQualifiedErrorId?: string | null
  stderrLineNumber?: number | null
  stderrColumnNumber?: number | null
  stderrSha256?: string | null
  windowFound?: boolean
  conversationObserved?: boolean
  conversationMatched?: boolean
  inputElementFound?: boolean
  valuePatternAvailable?: boolean
  textPatternAvailable?: boolean
  textObserved?: boolean
}

export interface PasteVerificationCapability {
  available: boolean
  reason: string | null
  providerInstanceId?: string
  diagnosticCode?: string | null
  capabilityCheckedAt?: string | null
  capabilityExpiresAt?: string | null
  capabilityAgeMs?: number | null
  capabilityProbeCount?: number
  capabilityProbeSpawnCount?: number
  lastCapabilityDiagnosticCode?: string | null
  capabilityProbeDiagnostic?: {
    scriptKind: 'availability_probe'
    spawnSucceeded: boolean
    timedOut: boolean
    exitCode: number | null
    stdoutJsonFound: boolean
    stderrCategory: PowerShellStderrCategory
    tempFileCreated: boolean
    scriptCleanupSucceeded?: boolean
    payloadCleanupSucceeded?: boolean
    tempFileCleanupSucceeded: boolean
    failureStep?: TaskVerificationFailureStep
    stderrFullyQualifiedErrorId?: string | null
    stderrLineNumber?: number | null
    stderrColumnNumber?: number | null
    stderrSha256?: string | null
  } | null
  method: string
  requiresManualConversationOpen: boolean
  supportedErrorCodes: string[]
}

export interface PasteVerificationProvider {
  getCapability: () => PasteVerificationCapability
  getCachedCapability?: () => PasteVerificationCapability
  refreshCapability?: (force?: boolean) => Promise<PasteVerificationCapability>
  verifyInputContent: (args: PasteVerificationArgs) => Promise<PasteInputObservationResult>
  verifyPasteContent?: (args: PasteVerificationArgs) => Promise<PasteInputObservationResult>
}
