import { getElectron } from '../electron-runtime'

export type ClipboardFormat = 'text' | 'html' | 'rtf' | 'image'

export interface ClipboardSnapshot {
  formats: ClipboardFormat[]
  unsupportedFormats?: string[]
  data: Record<string, string>
}

export interface NativeImageLike {
  isEmpty(): boolean
  toDataURL(): string
}

export interface ClipboardAdapter {
  availableFormats(): string[]
  readText(): string
  readHTML(): string
  readRTF(): string
  readImage(): NativeImageLike
  write(data: { text?: string; html?: string; rtf?: string; image?: unknown }): void
  writeText(text: string): void
}

const supportedFormatMatchers: Array<(format: string) => boolean> = [
  (format) => format.startsWith('text/plain'),
  (format) => format.startsWith('text/html'),
  (format) => format.startsWith('text/rtf'),
  (format) => format.startsWith('image/'),
]

function getClipboard(): ClipboardAdapter {
  return getElectron().clipboard as ClipboardAdapter
}

function isUnsupportedNativeFormat(format: string): boolean {
  const normalized = format.toLowerCase()
  if (normalized.includes('filename') || normalized.includes('file name') || normalized.includes('file-url')) return true
  if (normalized.startsWith('chromium ')) return false
  return !supportedFormatMatchers.some((matcher) => matcher(normalized))
}

export class ClipboardController {
  private readonly memoryOnly: boolean

  constructor(private snapshot?: ClipboardSnapshot, private readonly adapter?: ClipboardAdapter) {
    this.memoryOnly = adapter === undefined && snapshot !== undefined
  }

  inspectRestorable(): { ok: true; snapshot: ClipboardSnapshot } | { ok: false; errorCode: string; unsupportedFormats: string[] } {
    const snapshot = this.snapshot ? cloneSnapshot(this.snapshot) : this.readSystemSnapshot()
    const unsupportedFormats = [...(snapshot.unsupportedFormats ?? [])]
    if (unsupportedFormats.length) return { ok: false, errorCode: 'CLIPBOARD_FORMAT_UNSUPPORTED', unsupportedFormats }
    return { ok: true, snapshot }
  }

  async writeDraftText(text: string): Promise<void> {
    this.snapshot = { formats: ['text'], data: { text } }
    if (!this.memoryOnly) this.effectiveAdapter().writeText(text)
  }

  async restore(snapshot: ClipboardSnapshot): Promise<void> {
    if (snapshot.unsupportedFormats?.length) throw new Error('Cannot restore unsupported clipboard formats')
    this.snapshot = cloneSnapshot(snapshot)
    const imageDataUrl = snapshot.data.image
    if (!this.memoryOnly) {
      this.effectiveAdapter().write({
        text: snapshot.data.text,
        html: snapshot.data.html,
        rtf: snapshot.data.rtf,
        image: imageDataUrl ? getElectron().nativeImage.createFromDataURL(imageDataUrl) : undefined,
      })
    }
  }

  currentText(): string {
    return this.snapshot?.data.text ?? this.effectiveAdapter().readText()
  }

  private effectiveAdapter(): ClipboardAdapter {
    return this.adapter ?? getClipboard()
  }

  private readSystemSnapshot(): ClipboardSnapshot {
    const adapter = this.effectiveAdapter()
    const availableFormats = adapter.availableFormats()
    const unsupportedFormats = availableFormats.filter(isUnsupportedNativeFormat)
    if (unsupportedFormats.length) {
      return { formats: [], unsupportedFormats, data: {} }
    }
    const formats: ClipboardFormat[] = []
    const data: Record<string, string> = {}
    const text = adapter.readText()
    if (text) { formats.push('text'); data.text = text }
    const html = adapter.readHTML()
    if (html) { formats.push('html'); data.html = html }
    const rtf = adapter.readRTF()
    if (rtf) { formats.push('rtf'); data.rtf = rtf }
    const image = adapter.readImage()
    if (!image.isEmpty()) { formats.push('image'); data.image = image.toDataURL() }
    return { formats, data }
  }
}

function cloneSnapshot(snapshot: ClipboardSnapshot): ClipboardSnapshot {
  return {
    formats: [...snapshot.formats],
    unsupportedFormats: snapshot.unsupportedFormats ? [...snapshot.unsupportedFormats] : undefined,
    data: { ...snapshot.data },
  }
}
