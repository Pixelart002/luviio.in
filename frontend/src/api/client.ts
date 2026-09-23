import { request } from './request'

export { ApiError, getAccessToken, setAccessToken } from './request'

export type ApiProduct = {
  id: string
  name: string
  slug: string
  sku?: string
  price?: number | string
  selling_price?: number | string
  compare_price?: number | string
  image_url?: string | null
  images?: string[]
  category?: string
  category_name?: string
  stock_status?: string
  stock?: number
  short_description?: string
  description?: string
  specifications?: Record<string, string>
  [key: string]: unknown
}

export type ApiCategory = { id: string; name: string; slug?: string; image_url?: string }
export type ProductPage = { items: ApiProduct[]; total: number; page: number; page_size: number; pages?: number }
export type CartItem = {
  product_id: string
  product?: ApiProduct
  quantity: number
  unit_price?: number | string
  total?: number | string
}
export type Cart = { id?: string; items?: CartItem[]; subtotal?: number | string; total?: number | string; item_count?: number }
export type Session = { authenticated: boolean; user_id?: string; email?: string; expires_at?: number; profile?: Record<string, unknown> }

export type Address = {
  id: string
  full_name?: string
  phone?: string
  email?: string
  line1?: string
  line2?: string
  address_line1?: string
  address_line2?: string
  city?: string
  state?: string
  postal_code?: string
  country?: string
  landmark?: string
  address_type?: string
  company_name?: string
  gstin?: string
  is_default?: boolean
}

export type AddressInput = {
  line1: string
  line2?: string
  city: string
  state?: string
  postal_code: string
  country: string
  is_default?: boolean
  full_name?: string
  phone?: string
  email: string
  landmark?: string
  address_type?: string
  company_name?: string
  gstin?: string
}

export type Order = {
  id?: string
  order_number?: string
  status?: string
  payment_status?: string
  payment_intent_id?: string
  payment_provider?: string
  client_secret?: string
  total?: number | string
  subtotal?: number | string
  tax?: number | string
  shipping?: number | string
  discount?: number | string
  created_at?: string
  items?: Array<{ product_name?: string; quantity?: number; total?: number | string; unit_price?: number | string }>
  shipping_address?: Address
  [key: string]: unknown
}

export type PaymentIntentResult = {
  client_secret?: string
  payment_intent_id?: string
  order_number?: string
  payment_provider?: string
  [key: string]: unknown
}

const normalizePage = (payload: ProductPage | ApiProduct[] | { items?: ApiProduct[]; products?: ApiProduct[] }): ProductPage => {
  if (Array.isArray(payload)) return { items: payload, total: payload.length, page: 1, page_size: payload.length }
  const candidate = payload as { items?: ApiProduct[]; products?: ApiProduct[]; total?: number; page?: number; page_size?: number; pages?: number }
  const items = Array.isArray(candidate.items) ? candidate.items : Array.isArray(candidate.products) ? candidate.products : []
  return {
    items,
    total: candidate.total ?? items.length,
    page: candidate.page ?? 1,
    page_size: candidate.page_size ?? items.length,
    pages: candidate.pages,
  }
}

const normalizeCategories = (payload: ApiCategory[] | { items?: ApiCategory[]; categories?: ApiCategory[] }): ApiCategory[] => {
  if (Array.isArray(payload)) return payload
  return Array.isArray(payload.items) ? payload.items : Array.isArray(payload.categories) ? payload.categories : []
}

const normalizeAddresses = (payload: Address[] | { items?: Address[]; addresses?: Address[] }) => {
  if (Array.isArray(payload)) return payload
  return Array.isArray(payload.items) ? payload.items : Array.isArray(payload.addresses) ? payload.addresses : []
}

export const catalogApi = {
  categories: async () => normalizeCategories(await request<ApiCategory[] | { items?: ApiCategory[]; categories?: ApiCategory[] }>('GET', '/categories')),
  products: async (params = '') => normalizePage(await request<ProductPage | ApiProduct[] | { items?: ApiProduct[]; products?: ApiProduct[] }>('GET', `/products${params ? `?${params}` : ''}`)),
  product: (slug: string) => request<ApiProduct>('GET', `/products/${encodeURIComponent(slug)}`),
}

export const authApi = {
  login: (body: { email: string; password: string }) => request<Session>('POST', '/auth/login', body),
  register: (body: { email: string; password: string; full_name?: string }) => request('POST', '/auth/register', body),
  logout: () => request('POST', '/auth/logout', {}),
  session: () => request<Session>('GET', '/auth/session'),
}

export const cartApi = {
  get: () => request<Cart>('GET', '/cart'),
  add: (product_id: string, quantity = 1) => request<Cart>('POST', '/cart/items', { product_id, quantity }),
  update: (product_id: string, quantity: number) => request<Cart>('PUT', `/cart/items/${encodeURIComponent(product_id)}`, { quantity }),
  remove: (product_id: string) => request<Cart>('DELETE', `/cart/items/${encodeURIComponent(product_id)}`),
  clear: () => request<Cart>('DELETE', '/cart'),
}

export const ordersApi = {
  mine: (page = 1) => request<{ items: Order[]; total: number }>('GET', `/orders/my?page=${page}&page_size=20`),
  detail: (orderNumber: string) => request<Order>('GET', `/orders/my/${encodeURIComponent(orderNumber)}`),
  checkout: (shipping_address_id: string, idempotency_key: string, coupon_code?: string) =>
    request<Order>('POST', '/orders/checkout', { shipping_address_id, idempotency_key, coupon_code }),
  cod: (shipping_address_id: string, idempotency_key: string, coupon_code?: string) =>
    request<Order>('POST', '/orders/cod', { shipping_address_id, idempotency_key, coupon_code }),
  cancel: (orderNumber: string) => request<Order>('POST', `/orders/my/${encodeURIComponent(orderNumber)}/cancel`),
  invoice: async (orderNumber: string) => {
    const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
    const response = await fetch(`${API_BASE}/orders/${encodeURIComponent(orderNumber)}/invoice`, { credentials: 'include' })
    if (!response.ok) throw new Error(`Unable to download invoice (${response.status})`)
    return response.blob()
  },
}

export const paymentsApi = {
  createIntent: (body: { shipping_address_id: string; idempotency_key: string; coupon_code?: string; provider_key?: string }) =>
    request<PaymentIntentResult>('POST', '/payments/create-intent', body),
  confirm: (payment_intent_id: string, provider_key?: string) =>
    request<Order>('POST', '/payments/confirm', { payment_intent_id, provider_key }),
  retry: (orderNumber: string) => request<PaymentIntentResult>('POST', `/payments/retry/${encodeURIComponent(orderNumber)}`),
  cancel: (orderNumber: string) => request('POST', `/payments/cancel/${encodeURIComponent(orderNumber)}`),
  notifyFailed: (payment_intent_id: string, error_message: string, provider_key?: string) =>
    request('POST', '/payments/notify-failed', { payment_intent_id, error_message, provider_key }),
}

export const userApi = {
  me: () => request('GET', '/users/me'),
  addresses: async () => normalizeAddresses(await request<Address[] | { items?: Address[]; addresses?: Address[] }>('GET', '/users/me/addresses')),
  addAddress: (address: AddressInput) => request<Address>('POST', '/users/me/addresses', address),
  deleteAddress: (id: string) => request('DELETE', `/users/me/addresses/${encodeURIComponent(id)}`),
}

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
