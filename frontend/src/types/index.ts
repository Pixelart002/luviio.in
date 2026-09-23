import type { ApiProduct } from '../api/client'

export type Product = ApiProduct & {
  price: number
  image?: string
  category?: string
  description?: string
}
