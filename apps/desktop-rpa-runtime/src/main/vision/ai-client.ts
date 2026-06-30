import { ProviderHub } from './provider-hub'

export interface VisionIdentifyInput {
  imageBase64: string
  prompt: string
}

export interface VisionIdentifyResult {
  provider: string
  configured: boolean
  errorCode?: string
  confidence: number
  conversationName?: string | null
  candidates?: string[]
  resultCount?: number
  selectedResultIndex?: number
  resultRegion?: { x: number; y: number; width: number; height: number } | null
  durationMs?: number
}

export interface VisionAIClient {
  identify(input: VisionIdentifyInput): Promise<VisionIdentifyResult>
}

export class LocalVisionAIClient implements VisionAIClient {
  private readonly providerHub: ProviderHub

  constructor(providerHub?: ProviderHub) {
    this.providerHub = providerHub ?? new ProviderHub()
    this.providerHub.registerBuiltin({
      id: 'openai-compatible',
      name: 'OpenAI Compatible Vision',
      version: '1',
      local: true,
    })
  }

  async identify(input: VisionIdentifyInput): Promise<VisionIdentifyResult> {
    const config = this.providerHub.loadVisionConfig()
    if (!config.ok) {
      return {
        provider: 'none',
        configured: false,
        errorCode: config.errorCode,
        confidence: 0,
      }
    }

    const startedAt = Date.now()
    try {
      const apiKey = process.env[config.config.apiKeyEnv] ?? ''
      for (let attempt = 0; attempt <= config.config.maxRetries; attempt += 1) {
        try {
          const response = await fetch(config.config.baseUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${apiKey}`,
            },
            body: JSON.stringify({
              model: config.config.model,
              response_format: { type: 'json_object' },
              messages: [
                {
                  role: 'user',
                  content: [
                    { type: 'text', text: input.prompt },
                    { type: 'image_url', image_url: { url: `data:image/png;base64,${input.imageBase64}` } },
                  ],
                },
              ],
            }),
            signal: AbortSignal.timeout(config.config.timeoutMs),
          })
          if (!response.ok) {
            const errorCode = response.status === 408 || response.status === 504
              ? 'VISION_PROVIDER_TIMEOUT'
              : 'VISION_PROVIDER_UNAVAILABLE'
            if (attempt < config.config.maxRetries && errorCode === 'VISION_PROVIDER_UNAVAILABLE' && response.status >= 500) {
              continue
            }
            return {
              provider: config.config.providerId,
              configured: true,
              errorCode,
              confidence: 0,
              durationMs: Date.now() - startedAt,
            }
          }
          const payload = await response.json() as Record<string, unknown>
          const normalized = normalizeVisionPayload(payload)
          if (!normalized) {
            return {
              provider: config.config.providerId,
              configured: true,
              errorCode: 'VISION_RESPONSE_INVALID',
              confidence: 0,
              durationMs: Date.now() - startedAt,
            }
          }
          return {
            provider: config.config.providerId,
            configured: true,
            conversationName: normalized.conversationName,
            candidates: normalized.candidates,
            confidence: normalized.confidence,
            resultCount: normalized.resultCount,
            selectedResultIndex: normalized.selectedResultIndex,
            resultRegion: normalized.resultRegion,
            durationMs: Date.now() - startedAt,
          }
        } catch (error) {
          const errorCode = isTimeoutError(error) ? 'VISION_PROVIDER_TIMEOUT' : 'VISION_PROVIDER_UNAVAILABLE'
          if (attempt < config.config.maxRetries && errorCode === 'VISION_PROVIDER_UNAVAILABLE') {
            continue
          }
          return {
            provider: config.config.providerId,
            configured: true,
            errorCode,
            confidence: 0,
            durationMs: Date.now() - startedAt,
          }
        }
      }
    } catch {
      return {
        provider: config.config.providerId,
        configured: true,
        errorCode: 'VISION_PROVIDER_UNAVAILABLE',
        confidence: 0,
        durationMs: Date.now() - startedAt,
      }
    }
    return {
      provider: config.ok ? config.config.providerId : 'none',
      configured: config.ok,
      errorCode: 'VISION_PROVIDER_UNAVAILABLE',
      confidence: 0,
      durationMs: Date.now() - startedAt,
    }
  }
}

function normalizeVisionPayload(payload: Record<string, unknown>): {
  conversationName: string | null
  candidates: string[]
  confidence: number
  resultCount?: number
  selectedResultIndex?: number
  resultRegion?: { x: number; y: number; width: number; height: number } | null
} | null {
  const direct = normalizeVisionObject(payload)
  if (direct) return direct

  const choices = Array.isArray(payload.choices) ? payload.choices : []
  for (const choice of choices) {
    if (!choice || typeof choice !== 'object') continue
    const message = (choice as Record<string, unknown>).message
    if (!message || typeof message !== 'object') continue
    const content = (message as Record<string, unknown>).content
    const parsed = parseOpenAIContent(content)
    if (parsed) return parsed
  }
  return null
}

function parseOpenAIContent(content: unknown) {
  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content) as Record<string, unknown>
      return normalizeVisionObject(parsed)
    } catch {
      return null
    }
  }
  if (Array.isArray(content)) {
    for (const part of content) {
      if (!part || typeof part !== 'object') continue
      const text = (part as Record<string, unknown>).text
      if (typeof text !== 'string') continue
      try {
        const parsed = JSON.parse(text) as Record<string, unknown>
        const normalized = normalizeVisionObject(parsed)
        if (normalized) return normalized
      } catch {
        continue
      }
    }
  }
  return null
}

function normalizeVisionObject(payload: Record<string, unknown>) {
  const conversationName = typeof payload.conversationName === 'string' ? payload.conversationName : null
  const candidates = Array.isArray(payload.candidates)
    ? payload.candidates.filter((candidate): candidate is string => typeof candidate === 'string')
    : []
  const confidence = typeof payload.confidence === 'number' && Number.isFinite(payload.confidence) ? payload.confidence : 0
  const resultCount = typeof payload.resultCount === 'number' && Number.isFinite(payload.resultCount) ? payload.resultCount : undefined
  const selectedResultIndex = typeof payload.selectedResultIndex === 'number' && Number.isFinite(payload.selectedResultIndex) ? payload.selectedResultIndex : undefined
  const resultRegion = isRect(payload.resultRegion) ? payload.resultRegion : null
  if (!conversationName && !candidates.length && resultCount === undefined && resultRegion === null) return null
  return { conversationName, candidates, confidence, resultCount, selectedResultIndex, resultRegion }
}

function isRect(value: unknown): value is { x: number; y: number; width: number; height: number } {
  if (!value || typeof value !== 'object') return false
  const rect = value as Record<string, unknown>
  return ['x', 'y', 'width', 'height'].every((key) => typeof rect[key] === 'number' && Number.isFinite(rect[key]))
}

function isTimeoutError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const value = error as Record<string, unknown>
  return value.name === 'TimeoutError' || value.name === 'AbortError'
}
