const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, { ...options, credentials: 'include', headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(payload.detail) ? payload.detail.map((item: { msg?: string }) => item.msg).join(', ') : payload.detail
    throw new ApiError(detail || `Request failed (${response.status})`, response.status)
  }
  return payload.data ?? payload
}

export type ApiProduct = { id: string; name: string; slug: string; sku?: string; price?: number; selling_price?: number; images?: string[]; category?: string; category_name?: string; stock_status?: string; short_description?: string; description?: string; specifications?: Record<string, string> }
export type ApiCategory = { id: string; name: string; slug?: string; image_url?: string }
export type ProductPage = { items: ApiProduct[]; total: number; page: number; page_size: number; pages?: number }
export type Cart = { id?: string; items?: Array<{ product_id: string; product?: ApiProduct; quantity: number; unit_price?: number; total?: number }>; subtotal?: number; total?: number; item_count?: number }
export type Session = { authenticated: boolean; user_id?: string; email?: string; expires_at?: number }

export const catalogApi = {
  categories: () => api<ApiCategory[]>('/categories'),
  products: (params = '') => api<ProductPage>(`/products${params ? `?${params}` : ''}`),
  product: (slug: string) => api<ApiProduct>(`/products/${encodeURIComponent(slug)}`),
}
export const authApi = {
  login: (body: { email: string; password: string }) => api('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  register: (body: { email: string; password: string; full_name?: string }) => api('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => api('/auth/logout', { method: 'POST' }),
  session: () => api<Session>('/auth/session'),
}
export const cartApi = {
  get: () => api<Cart>('/cart'),
  add: (product_id: string, quantity = 1) => api<Cart>('/cart/items', { method: 'POST', body: JSON.stringify({ product_id, quantity }) }),
  update: (product_id: string, quantity: number) => api<Cart>(`/cart/items/${product_id}`, { method: 'PUT', body: JSON.stringify({ quantity }) }),
  remove: (product_id: string) => api<Cart>(`/cart/items/${product_id}`, { method: 'DELETE' }),
  clear: () => api('/cart', { method: 'DELETE' }),
}
export const ordersApi = {
  mine: (page = 1) => api<{ items: unknown[]; total: number }>(`/orders/my?page=${page}&page_size=20`),
  checkout: (shipping_address_id: string, idempotency_key: string, coupon_code?: string) => api('/orders/checkout', { method: 'POST', body: JSON.stringify({ shipping_address_id, idempotency_key, coupon_code }) }),
  cod: (shipping_address_id: string, idempotency_key: string, coupon_code?: string) => api('/orders/cod', { method: 'POST', body: JSON.stringify({ shipping_address_id, idempotency_key, coupon_code }) }),
}
export const apiBaseUrl = API_BASE
