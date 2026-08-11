import { describe, expect, test } from 'vitest'
import { redactSensitiveText, redactSensitiveValue } from '../privacy-redaction'

describe('desktop privacy redaction', () => {
  test('redacts bearer tokens, secret assignments, URL tokens, and user home paths', () => {
    const input = 'Bearer abc.def token=secret /Users/alice/private https://x.test?a=1&access_token=xyz'

    const redacted = redactSensitiveText(input)

    expect(redacted).not.toContain('abc.def')
    expect(redacted).not.toContain('secret')
    expect(redacted).not.toContain('/Users/alice/')
    expect(redacted).not.toContain('access_token=xyz')
    expect(redacted).toContain('[REDACTED]')
  })

  test('recursively redacts sensitive object keys', () => {
    const redacted = redactSensitiveValue({
      authorization: 'Bearer token',
      nested: { api_key: 'key-value', path: '/Users/bob/project/file.ts' },
    })

    expect(redacted).toEqual({
      authorization: '[REDACTED]',
      nested: { api_key: '[REDACTED]', path: '/Users/[USER]/project/file.ts' },
    })
  })
})
