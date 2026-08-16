const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const CONTENT_TYPE_JSON = 'application/json'

type DesktopProfileResolver = () => { apiBaseUrl?: string; authToken?: string } | null

let desktopProfileResolver: DesktopProfileResolver | null = null
let localRuntimeBaseUrl: string | null = null

export function setDesktopProfileResolver(resolver: DesktopProfileResolver | null): void {
  desktopProfileResolver = resolver
}

export function setLocalRuntimeBaseUrl(baseUrl: string | null): void {
  localRuntimeBaseUrl = baseUrl
}

export function getApiBaseUrl(): string {
  return localRuntimeBaseUrl || process.env.API_BASE_URL || desktopProfileResolver?.()?.apiBaseUrl || DEFAULT_API_BASE_URL
}

export function getAuthToken(): string {
  return process.env.AUTH_TOKEN || desktopProfileResolver?.()?.authToken || ''
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${getApiBaseUrl()}${endpoint}`
  const token = getAuthToken()

  const response = await resolveFetch()(url, {
    ...options,
    ...(localRuntimeBaseUrl ? { credentials: 'include' as const } : {}),
    headers: {
      'Content-Type': CONTENT_TYPE_JSON,
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
  })

  if (!response.ok) {
    throw new Error(
      `API request failed: ${response.status} ${response.statusText}`
    )
  }

  const data = await response.json()
  return data as T
}

function resolveFetch(): typeof fetch {
  if (!localRuntimeBaseUrl) return fetch
  try {
    const electronNet = (require('electron') as { net?: { fetch?: typeof fetch } }).net
    if (typeof electronNet?.fetch === 'function') return electronNet.fetch.bind(electronNet)
  } catch {
    // Tests and non-Electron consumers use the platform fetch implementation.
  }
  return fetch
}

export function buildQueryString(params: Record<string, string | undefined>): string {
  const searchParams = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      searchParams.set(key, value)
    }
  }
  const queryString = searchParams.toString()
  return queryString ? `?${queryString}` : ''
}
