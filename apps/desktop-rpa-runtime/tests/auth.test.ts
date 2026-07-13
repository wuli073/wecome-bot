import assert from 'node:assert/strict'
import test from 'node:test'
import { assertBearerAuth } from '../src/main/api/auth'

test('assertBearerAuth accepts the expected token', () => {
  assert.doesNotThrow(() => {
    assertBearerAuth({ headers: { authorization: 'Bearer secret-token' } } as never, 'secret-token')
  })
})

test('assertBearerAuth rejects missing and mismatched tokens', () => {
  assert.throws(() => assertBearerAuth({ headers: {} } as never, 'secret-token'))
  assert.throws(() => assertBearerAuth({ headers: { authorization: 'Bearer wrong' } } as never, 'secret-token'))
})
