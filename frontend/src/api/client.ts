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
  id: string
  product_id: string
  name: string
  slug: string
  image_url?: string | null
  hsn_code?: string
  gst_percentage?: number
  quantity: number
  unit_price: number | string
  current_unit_price?: number | string
  compare_price?: number | string
  price_snapshot?: number | string
  line_total: number | string
  weight?: number | string | null
  weight_unit?: 'g' | 'kg' | string | null
  stock?: number
  in_stock?: boolean
  is_active?: boolean
  price_changed?: boolean
  added_at?: string
}
export type Cart = {
  items: CartItem[]
  item_count: number
  subtotal: number | string
  shipping_cost: number | string
  tax_amount: number | string
  total_amount: number | string
  free_shipping_eligible: boolean
  amount_to_free_shipping: number | string
  free_shipping_threshold: number | string
  has_unavailable_items: boolean
  shipping_calculated_at_checkout?: boolean
  currency?: string
}

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

export type OrderItem = {
  name?: string
  product_name?: string
  product_slug?: string
  product_image_url?: string | null
  sku?: string
  quantity?: number
  unit_price?: number | string
  line_total?: number | string
  total?: number | string
  gst_percentage?: number
  hsn_code?: string
}
export type Order = {
  id?: string
  order_number?: string
  status?: string
  payment_status?: string
  payment_intent_id?: string
  payment_provider?: string
  payment_method?: string
  client_secret?: string
  subtotal?: number | string
  shipping_cost?: number | string
  shipping_tax_amount?: number | string
  tax_amount?: number | string
  discount_amount?: number | string
  total_amount?: number | string
  currency?: string
  created_at?: string
  shipped_at?: string
  delivered_at?: string
  tracking_number?: string | null
  shipping_provider?: string | null
  shipping_courier_id?: number | string | null
  shipping_courier_name?: string | null
  shipping_service_type?: string | null
  shipping_delivery_mode?: string | null
  shipping_vehicle_type?: string | null
  shipping_name?: string | null
  shipping_phone?: string | null
  shipping_email?: string | null
  shipping_line1?: string | null
  shipping_line2?: string | null
  shipping_landmark?: string | null
  shipping_city?: string | null
  shipping_state?: string | null
  shipping_postal_code?: string | null
  shipping_country?: string | null
  shipping_company_name?: string | null
  shipping_gstin?: string | null
  order_items?: OrderItem[]
  items?: OrderItem[]
  [key: string]: unknown
}
export type ShippingQuote = {
  courier_id?: number | string
  courier_name?: string
  service_type?: string | null
  provider_mode?: string | null
  delivery_mode?: string | null
  vehicle_type?: string | null
  quick_delivery?: boolean
  shipping_cost: number | string
  provider_rate?: number | string
  freight_charge?: number | string
  cod_charge?: number | string
  other_charges?: number | string
  coverage_charges?: number | string
  discount?: number | string
  chargeable_weight_kg?: number | string | null
  estimated_delivery_days?: number | string | null
  etd_hours?: number | string | null
  etd?: string | null
  rating?: number | string | null
}
export type ShippingRateResult = {
  provider?: string
  pickup_postcode?: string
  delivery_postcode?: string
  weight_kg?: number | string
  cod?: boolean
  declared_value?: number | string
  selected?: ShippingQuote
  selection?: string
  quotes?: ShippingQuote[]
  couriers?: ShippingQuote[]
}
export type Shipment = {
  id?: string
  order_id?: string
  provider_key?: string
  status?: string
  provider_status?: string
  workflow_status?: string
  tracking_number?: string | null
  tracking_url?: string | null
  courier_name?: string | null
  courier_id?: number | string | null
  service_type?: string | null
  pickup_id?: string | null
  external_order_id?: string | null
  external_shipment_id?: string | null
  awb_assigned_at?: string | null
  pickup_scheduled_at?: string | null
  shipped_at?: string | null
  delivered_at?: string | null
  label_url?: string | null
  manifest_url?: string | null
  provider_invoice_url?: string | null
  created_at?: string
  updated_at?: string
  metadata?: Record<string, unknown>
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
  checkout: (shipping_address_id: string, idempotency_key: string, coupon_code?: string, shipping_courier_id?: number) =>
    request<Order>('POST', '/orders/checkout', { shipping_address_id, idempotency_key, coupon_code, shipping_courier_id }),
  cod: (shipping_address_id: string, idempotency_key: string, coupon_code?: string, shipping_courier_id?: number) =>
    request<Order>('POST', '/orders/cod', { shipping_address_id, idempotency_key, coupon_code, shipping_courier_id }),
  cancel: (orderNumber: string) => request<Order>('POST', `/orders/my/${encodeURIComponent(orderNumber)}/cancel`),
  invoice: async (orderNumber: string) => {
    const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
    const headers: Record<string, string> = {}
    const token = getAccessToken()
    if (token) headers.Authorization = `Bearer ${token}`
    const response = await fetch(`${API_BASE}/orders/${encodeURIComponent(orderNumber)}/invoice`, { credentials: 'include', headers })
    if (!response.ok) throw new Error(`Unable to download invoice (${response.status})`)
    return response.blob()
  },
}

export const paymentsApi = {
  createIntent: (body: { shipping_address_id: string; idempotency_key: string; coupon_code?: string; shipping_courier_id?: number; provider_key?: string }) =>
    request<PaymentIntentResult>('POST', '/payments/create-intent', body),
  confirm: (payment_intent_id: string, provider_key?: string) =>
    request<Order>('POST', '/payments/confirm', { payment_intent_id, provider_key }),
  retry: (orderNumber: string) => request<PaymentIntentResult>('POST', `/payments/retry/${encodeURIComponent(orderNumber)}`),
  cancel: (orderNumber: string) => request('POST', `/payments/cancel/${encodeURIComponent(orderNumber)}`),
  notifyFailed: (payment_intent_id: string, error_message: string, provider_key?: string) =>
    request('POST', '/payments/notify-failed', { payment_intent_id, error_message, provider_key }),
}

export const shippingApi = {
  rate: (delivery_postcode: string, weight_kg: number, cod: boolean, declared_value?: number) => {
    const query = new URLSearchParams({
      delivery_postcode,
      weight_kg: String(Math.max(weight_kg, 0.1)),
      cod: String(cod),
      ...(declared_value !== undefined ? { declared_value: String(Math.max(declared_value, 0)) } : {}),
    })
    return request<ShippingRateResult>('GET', `/shipping/provider/rate?${query.toString()}`)
  },
  mine: (orderNumber: string) => request<Shipment | { status: string }>('GET', `/shipping/my/${encodeURIComponent(orderNumber)}`),
}

export const userApi = {
  me: () => request('GET', '/users/me'),
  addresses: async () => normalizeAddresses(await request<Address[] | { items?: Address[]; addresses?: Address[] }>('GET', '/users/me/addresses')),
  addAddress: (address: AddressInput) => request<Address>('POST', '/users/me/addresses', address),
  deleteAddress: (id: string) => request('DELETE', `/users/me/addresses/${encodeURIComponent(id)}`),
}

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
