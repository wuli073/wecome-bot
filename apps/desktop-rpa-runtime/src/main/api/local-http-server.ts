import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import { RuntimeHttpError } from '../domain/error-types'
import type { RuntimeStateStore } from '../runtime/state-store'
import { RuntimeHost } from '../runtime/runtime-host'
import { assertBearerAuth } from './auth'
import { buildHealthPayload } from './routes-health'
import { buildRuntimeStatusPayload } from './routes-runtime'

function writeJson(response: ServerResponse, statusCode: number, payload: unknown): void {
  response.statusCode = statusCode
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.end(JSON.stringify(payload))
}

function normalizePath(request: IncomingMessage): string {
  return new URL(request.url ?? '/', 'http://127.0.0.1').pathname
}

async function readBody(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = []
  for await (const chunk of request) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  const raw = Buffer.concat(chunks).toString('utf8').trim()
  if (!raw) return {}
  const parsed = JSON.parse(raw)
  return parsed && typeof parsed === 'object' ? parsed : {}
}

function toAction(path: string) {
  if (path.endsWith('/send-draft')) return 'send_draft'
  if (path.endsWith('/diagnose')) return 'diagnose'
  if (path.endsWith('/conversation-search')) return 'conversation_search'
  if (path.endsWith('/history-search')) return 'history_search'
  if (path.endsWith('/quote-reply')) return 'quote_reply'
  return 'paste_draft'
}

export async function createLocalHttpServer(options: {
  host: string
  port: number
  token: string
  stateStore: RuntimeStateStore
  runtimeHost?: RuntimeHost
}): Promise<{ port: number; close: () => Promise<void> }> {
  const runtimeHost = options.runtimeHost ?? new RuntimeHost({
    runtimeAutoSendEnabled: process.env.LANGBOT_RPA_ALLOW_AUTO_SEND === '1',
    sendDriverForceDisabled: process.env.LANGBOT_RPA_FORCE_DISABLE_SEND === '1',
  })
  const server = createServer((request, response) => {
    void (async () => {
      try {
        assertBearerAuth(request, options.token)
        const path = normalizePath(request)
        if (request.method === 'GET' && path === '/healthz') {
          writeJson(response, 200, buildHealthPayload(options.stateStore))
          return
        }
        if (request.method === 'GET' && path === '/v1/runtime/status') {
          writeJson(response, 200, { ...buildRuntimeStatusPayload(options.stateStore), activeTaskCount: runtimeHost.activeTaskCount() })
          return
        }
        if (request.method === 'POST' && /^\/v1\/tasks\/(paste-draft|send-draft|diagnose|conversation-search|history-search|quote-reply)$/.test(path)) {
          const body = await readBody(request)
          const action = toAction(path)
          if (action === 'paste_draft') assertPasteDraftBodyShape(body)
          const task = await runtimeHost.createTask({
            ...body,
            action,
            idempotencyKey: String(body.idempotencyKey ?? `${Date.now()}-${Math.random()}`),
            requestDigest: String(body.requestDigest ?? ''),
          } as never)
          writeJson(response, 200, task)
          return
        }
        const taskGet = path.match(/^\/v1\/tasks\/([^/]+)$/)
        if (request.method === 'GET' && taskGet) {
          const task = runtimeHost.getTask(taskGet[1])
          if (!task) throw new RuntimeHttpError(404, 'TASK_NOT_FOUND', 'Task not found')
          writeJson(response, 200, task)
          return
        }
        const taskCancel = path.match(/^\/v1\/tasks\/([^/]+)\/cancel$/)
        if (request.method === 'POST' && taskCancel) {
          const task = runtimeHost.cancelTask(taskCancel[1])
          if (!task) throw new RuntimeHttpError(404, 'TASK_NOT_FOUND', 'Task not found')
          writeJson(response, 200, task)
          return
        }
        if (request.method === 'POST' && (path === '/v1/polling/start' || path === '/v1/polling/stop')) {
          writeJson(response, 200, { status: path.endsWith('/start') ? 'started' : 'stopped' })
          return
        }
        throw new RuntimeHttpError(404, 'NOT_FOUND', `Unknown route: ${request.method} ${path}`)
      } catch (error) {
        if (error instanceof RuntimeHttpError) {
          writeJson(response, error.statusCode, { errorCode: error.errorCode, message: error.message })
          return
        }
        writeJson(response, 500, { errorCode: 'INTERNAL_ERROR', message: error instanceof Error ? error.message : String(error) })
      }
    })()
  })

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(options.port, options.host, () => resolve())
  })

  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Expected TCP server address')
  return { port: address.port, close: () => new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())) }
}

function assertPasteDraftBodyShape(body: Record<string, unknown>) {
  const allowedFields = new Set(['action', 'conversationName', 'draftText', 'idempotencyKey', 'requestDigest'])
  for (const key of Object.keys(body)) {
    if (!allowedFields.has(key)) throw new RuntimeHttpError(400, 'UNEXPECTED_REQUEST_FIELD', `Unexpected paste-draft field: ${key}`)
  }
}
