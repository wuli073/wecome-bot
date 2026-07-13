export interface ConversationVerificationResult {
  ok: boolean
  errorCode?: string
  confidence?: number
  observedConversation?: string | null
  candidates?: string[]
  normalizedExpected?: string
  normalizedObserved?: string
}

export interface VisionConversationAnalysis {
  configured?: boolean
  errorCode?: string
  confidence?: number
  conversationName?: string | null
  candidates?: string[] | null
}

const MEMBER_SUFFIX_PATTERNS = [
  /\(\s*\d+\s*\)$/u,
  /（\s*\d+\s*）$/u,
]

export function normalizeConversationName(value: string, options: { stripMemberCountSuffix?: boolean } = {}): string {
  let normalized = value.normalize('NFKC').trim().replace(/\s+/gu, ' ')
  if (options.stripMemberCountSuffix ?? true) {
    for (const pattern of MEMBER_SUFFIX_PATTERNS) {
      normalized = normalized.replace(pattern, '').trim()
    }
  }
  return normalized
}

export function verifyConversationName(expected: string, observed: string): ConversationVerificationResult {
  const normalizedExpected = normalizeConversationName(expected)
  if (!normalizedExpected) {
    return { ok: false, errorCode: 'CONVERSATION_UNVERIFIABLE', normalizedExpected }
  }
  const normalizedObserved = normalizeConversationName(observed)
  if (!normalizedObserved) {
    return { ok: false, errorCode: 'CONVERSATION_UNVERIFIABLE', normalizedExpected, normalizedObserved }
  }
  if (normalizedExpected === normalizedObserved) {
    return { ok: true, normalizedExpected, normalizedObserved }
  }
  return {
    ok: false,
    errorCode: 'CONVERSATION_MISMATCH',
    normalizedExpected,
    normalizedObserved,
    observedConversation: normalizedObserved,
  }
}

export function interpretConversationVerification(
  expectedConversation: string,
  analysis: VisionConversationAnalysis,
): ConversationVerificationResult {
  if (!analysis.configured || analysis.errorCode === 'VISION_PROVIDER_NOT_CONFIGURED') {
    return {
      ok: false,
      errorCode: 'VISION_PROVIDER_NOT_CONFIGURED',
      confidence: 0,
      candidates: [],
      observedConversation: null,
    }
  }
  const confidence = Number.isFinite(analysis.confidence) ? Number(analysis.confidence) : 0
  const candidates = (analysis.candidates ?? [])
    .filter((candidate): candidate is string => typeof candidate === 'string')
    .map((candidate) => normalizeConversationName(candidate))
    .filter(Boolean)
  if (candidates.length > 1) {
    return {
      ok: false,
      errorCode: 'CONVERSATION_AMBIGUOUS',
      confidence,
      candidates,
      observedConversation: null,
    }
  }
  const observedConversation = typeof analysis.conversationName === 'string'
    ? normalizeConversationName(analysis.conversationName)
    : candidates[0] ?? null
  if (!observedConversation) {
    return {
      ok: false,
      errorCode: 'CONVERSATION_UNVERIFIABLE',
      confidence,
      candidates,
      observedConversation: null,
    }
  }
  if (confidence < 0.5) {
    return {
      ok: false,
      errorCode: 'CONVERSATION_VERIFICATION_UNCERTAIN',
      confidence,
      candidates: candidates.length ? candidates : [observedConversation],
      observedConversation,
    }
  }
  return {
    ...verifyConversationName(expectedConversation, observedConversation),
    confidence,
    candidates: candidates.length ? candidates : [observedConversation],
    observedConversation,
  }
}
