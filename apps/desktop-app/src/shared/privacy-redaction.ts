const REDACTED = '[REDACTED]'

export function redactSensitiveText(value: string): string {
  return value
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, `Bearer ${REDACTED}`)
    .replace(/([?&](?:access_token|auth_token|api_key|token)=)[^&#\s]+/gi, `$1${REDACTED}`)
    .replace(/\b((?:api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|token|password)\s*[:=]\s*)[^\s,;]+/gi, `$1${REDACTED}`)
    .replace(/\/Users\/[^/\s]+\//g, '/Users/[USER]/')
    .replace(/\\Users\\[^\\\s]+\\/gi, '\\Users\\[USER]\\')
}

export function redactSensitiveValue<T>(value: T, seen = new WeakSet<object>()): T {
  if (typeof value === 'string') return redactSensitiveText(value) as T
  if (value === null || typeof value !== 'object') return value
  if (seen.has(value)) return REDACTED as T
  seen.add(value)

  if (Array.isArray(value)) {
    return value.map((item) => redactSensitiveValue(item, seen)) as T
  }

  const output: Record<string, unknown> = {}
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    output[key] = isSensitiveKey(key) ? REDACTED : redactSensitiveValue(item, seen)
  }
  return output as T
}

function isSensitiveKey(key: string): boolean {
  return /^(?:authorization|password|api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|token|secret)$/i.test(key)
}
