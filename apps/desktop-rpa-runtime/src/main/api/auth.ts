import type { IncomingMessage } from 'node:http'
import { RuntimeHttpError } from '../domain/error-types'

const BEARER_PREFIX = 'Bearer '

export function assertBearerAuth(request: IncomingMessage, expectedToken: string): void {
  const authorization = request.headers.authorization
  if (!authorization || !authorization.startsWith(BEARER_PREFIX)) {
    throw new RuntimeHttpError(401, 'RUNTIME_UNAUTHORIZED', 'Missing bearer token')
  }
  const token = authorization.slice(BEARER_PREFIX.length)
  if (!token || token !== expectedToken) {
    throw new RuntimeHttpError(401, 'RUNTIME_UNAUTHORIZED', 'Invalid bearer token')
  }
}
