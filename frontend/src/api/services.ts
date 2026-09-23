import { request } from './request'
import type { ApiCategory, ApiProduct, ProductPage } from './client'

const params = (values: Record<string, unknown>) => {
  const query = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== null && value !== '') query.set(key, String(value)) })
  const text = query.toString()
  return text ? `?${text}` : ''
}

const asArray = <T>(value: T[] | { items?: T[]; products?: T[]; categories?: T[] } | undefined): T[] => Array.isArray(value) ? value : value?.items || (value as any)?.products || (value as any)?.categories || []

export const productService = {
  list: async (filters: Record<string, unknown> = {}) => {
    const value = await request<ProductPage | ApiProduct[] | { items?: ApiProduct[]; products?: ApiProduct[] }>('GET', `/products${params(filters)}`)
    const items = asArray<ApiProduct>(value)
    return { items, total: (value as ProductPage)?.total ?? items.length, page: (value as ProductPage)?.page ?? 1, pages: (value as ProductPage)?.pages }
  },
  get: (slug: string) => request<ApiProduct>('GET', `/products/${encodeURIComponent(slug)}`),
  categories: async () => asArray<ApiCategory>(await request<ApiCategory[] | { items?: ApiCategory[]; categories?: ApiCategory[] }>('GET', '/categories')),
}

export const authService = {
  register: (email: string, password: string, fullName?: string) => request('POST', '/auth/register', { email, password, full_name: fullName }),
  login: (email: string, password: string) => request('POST', '/auth/login', { email, password }),
  logout: () => request('POST', '/auth/logout', {}),
  session: () => request('GET', '/auth/session'),
}

export const cartService = {
  get: () => request('GET', '/cart'),
  addItem: (productId: string, quantity: number) => request('POST', '/cart/items', { product_id: productId, quantity }),
  updateItem: (productId: string, quantity: number) => request('PUT', `/cart/items/${encodeURIComponent(productId)}`, { quantity }),
  removeItem: (productId: string) => request('DELETE', `/cart/items/${encodeURIComponent(productId)}`),
  clear: () => request('DELETE', '/cart'),
}

export const orderService = {
  mine: (page = 1, pageSize = 10) => request('GET', `/orders/my?page=${page}&page_size=${pageSize}`),
  get: (orderNumber: string) => request('GET', `/orders/my/${encodeURIComponent(orderNumber)}`),
  checkout: (shippingAddressId: string, notes?: string, idempotencyKey?: string) => request('POST', '/orders/checkout', { shipping_address_id: shippingAddressId, notes, idempotency_key: idempotencyKey }),
}
