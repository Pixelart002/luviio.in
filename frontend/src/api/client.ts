const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include', headers: { 'Content-Type': 'application/json', ...options.headers }, ...options })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || 'Something went wrong')
  return payload.data ?? payload
}

export type ApiProduct = { id: string; name: string; slug: string; price?: number; selling_price?: number; images?: string[]; category?: string; stock_status?: string; short_description?: string }
export type ApiCategory = { id: string; name: string; slug?: string; image_url?: string }
export type ProductPage = { items: ApiProduct[]; total: number; page: number; page_size: number; pages?: number }

export const catalogApi = {
  categories: () => api<ApiCategory[]>('/categories'),
  products: (params = '') => api<ProductPage>(`/products${params ? `?${params}` : ''}`),
  product: (slug: string) => api<ApiProduct>(`/products/${slug}`),
}

export const authApi = { login: (body: object) => api('/auth/login', { method: 'POST', body: JSON.stringify(body) }), register: (body: object) => api('/auth/register', { method: 'POST', body: JSON.stringify(body) }), logout: () => api('/auth/logout', { method: 'POST' }), session: () => api('/auth/session') }
export const cartApi = { get: () => api('/cart'), add: (product_id: string, quantity: number) => api('/cart/items', { method: 'POST', body: JSON.stringify({ product_id, quantity }) }) }
