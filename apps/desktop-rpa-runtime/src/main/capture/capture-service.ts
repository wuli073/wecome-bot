import { getElectron } from '../electron-runtime'
import { logicalToPhysicalRect } from './dpi-transform'

export interface ScreenshotPayload {
  pngBase64: string
  displayId: string | number
  scaleFactor: number
  boundsLogical: { x: number; y: number; width: number; height: number }
  capturedAt: string
}

export class CaptureService {
  async captureRegion(
    boundsLogical: { x: number; y: number; width: number; height: number },
    displayId?: string | number,
    scaleFactor?: number,
  ): Promise<ScreenshotPayload> {
    const { desktopCapturer, nativeImage, screen } = getElectron()
    const display = displayId === undefined
      ? screen.getDisplayMatching(boundsLogical)
      : screen.getAllDisplays().find((candidate: { id: string | number }) => String(candidate.id) === String(displayId)) ?? screen.getDisplayMatching(boundsLogical)
    const actualScaleFactor = scaleFactor ?? display.scaleFactor
    const physicalDisplaySize = {
      width: Math.ceil(display.bounds.width * actualScaleFactor),
      height: Math.ceil(display.bounds.height * actualScaleFactor),
    }
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: physicalDisplaySize,
      fetchWindowIcons: false,
    })
    const source = sources.find((candidate: { display_id?: string }) => String(candidate.display_id) === String(display.id)) ?? sources[0]
    if (!source || source.thumbnail.isEmpty()) {
      throw new Error('CAPTURE_SOURCE_UNAVAILABLE')
    }

    const physicalRect = logicalToPhysicalRect(
      {
        x: boundsLogical.x - display.bounds.x,
        y: boundsLogical.y - display.bounds.y,
        width: boundsLogical.width,
        height: boundsLogical.height,
      },
      actualScaleFactor,
    )
    const size = source.thumbnail.getSize()
    const x = Math.max(0, Math.min(size.width - 1, physicalRect.x))
    const y = Math.max(0, Math.min(size.height - 1, physicalRect.y))
    const width = Math.max(1, Math.min(size.width - x, physicalRect.width))
    const height = Math.max(1, Math.min(size.height - y, physicalRect.height))
    const cropped = nativeImage.createFromBuffer(source.thumbnail.crop({ x, y, width, height }).toPNG())
    return {
      pngBase64: cropped.toPNG().toString('base64'),
      displayId: display.id,
      scaleFactor: actualScaleFactor,
      boundsLogical: { ...boundsLogical },
      capturedAt: new Date().toISOString(),
    }
  }
}
