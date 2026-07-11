export interface LocalProviderManifest {
  id: string
  name: string
  version: string
  local: true
}

export interface VisionProviderConfig {
  providerId: string
  baseUrl: string
  model: string
  apiKeyEnv: string
  timeoutMs: number
  maxRetries: number
}

export class ProviderHub {
  private readonly providers = new Map<string, LocalProviderManifest>()

  registerBuiltin(manifest: LocalProviderManifest): void {
    this.providers.set(manifest.id, manifest)
  }

  getProvider(id: string): LocalProviderManifest | null {
    return this.providers.get(id) ?? null
  }

  listProviders(): LocalProviderManifest[] {
    return [...this.providers.values()]
  }

  loadVisionConfig(): { ok: true; config: VisionProviderConfig } | { ok: false; errorCode: string } {
    const providerId = (process.env.LANGBOT_RPA_VISION_PROVIDER_ID ?? '').trim()
    const baseUrl = (process.env.LANGBOT_RPA_VISION_BASE_URL ?? '').trim()
    const model = (process.env.LANGBOT_RPA_VISION_MODEL ?? '').trim()
    const apiKeyEnv = (process.env.LANGBOT_RPA_VISION_API_KEY_ENV ?? '').trim()
    const timeoutMs = Number(process.env.LANGBOT_RPA_VISION_TIMEOUT_MS ?? '10000')
    const maxRetries = Number(process.env.LANGBOT_RPA_VISION_MAX_RETRIES ?? '1')

    if (!providerId || !baseUrl || !model || !apiKeyEnv) {
      return { ok: false, errorCode: 'VISION_PROVIDER_NOT_CONFIGURED' }
    }
    if (!this.getProvider(providerId)) {
      return { ok: false, errorCode: 'VISION_PROVIDER_NOT_CONFIGURED' }
    }
    if (!/^https?:\/\//u.test(baseUrl)) {
      return { ok: false, errorCode: 'VISION_PROVIDER_INVALID_CONFIG' }
    }
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || !Number.isFinite(maxRetries) || maxRetries < 0) {
      return { ok: false, errorCode: 'VISION_PROVIDER_INVALID_CONFIG' }
    }
    if (!(process.env[apiKeyEnv] ?? '').trim()) {
      return { ok: false, errorCode: 'VISION_PROVIDER_NOT_CONFIGURED' }
    }

    return {
      ok: true,
      config: {
        providerId,
        baseUrl,
        model,
        apiKeyEnv,
        timeoutMs,
        maxRetries,
      },
    }
  }
}
