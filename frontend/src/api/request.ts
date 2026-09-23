const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export class ApiError extends Error {
  status: number
  code?: string
  constructor(message: string, status = 0, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

let accessToken: string | null = null
let refreshPromise: Promise<string | null> | null = null

export function setAccessToken(token: string | null) { accessToken = token || null }
export function getAccessToken() { return accessToken }

function unwrap(json: any) {
  if (json?.success === undefined || json?.data === undefined) return json
  if (json.meta === undefined) return json.data
  return Array.isArray(json.data) ? Object.assign(json.data, { meta: json.meta }) : { ...json.data, meta: json.meta }
}

async function refreshToken() {
  if (refreshPromise) return refreshPromise
  refreshPromise = fetch(`${API_BASE}/auth/refresh`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' } })
    .then(async (res) => res.ok ? ((await res.json())?.data?.access_token ?? null) : null)
    .catch(() => null)
    .finally(() => { refreshPromise = null })
  return refreshPromise
}

export async function request<T>(method: string, path: string, body?: unknown, retried = false): Promise<T> {
  const headers: Record<string, string> = {}
  if (accessToken && !path.startsWith('/auth/')) headers.Authorization = `Bearer ${accessToken}`
  if (body !== undefined) { headers['Content-Type'] = 'application/json' }
  const response = await fetch(`${API_BASE}${path}`, { method, headers, credentials: 'include', body: body === undefined ? undefined : JSON.stringify(body) })
  if (response.status === 401 && !retried && !path.startsWith('/auth/')) {
    const token = await refreshToken()
    if (token) { setAccessToken(token); return request<T>(method, path, body, true) }
  }
  const json = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = Array.isArray(json?.detail) ? json.detail.map((item: any) => item.msg || item.message).join('; ') : json?.message || json?.detail || `Request failed (${response.status})`
    throw new ApiError(String(detail), response.status, json?.error_code)
  }
  return unwrap(json) as T
}
