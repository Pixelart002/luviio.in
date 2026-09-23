/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_STRIPE_PUBLISHABLE_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

type StripeCardElement = {
  mount: (selector: string) => void
  destroy: () => void
  on: (event: 'ready' | 'change', handler: (event: { error?: { message?: string } }) => void) => void
}

type StripeElements = {
  create: (type: 'card', options?: { hidePostalCode?: boolean }) => StripeCardElement
  getElement: (type: 'card') => StripeCardElement | null
}

type StripeInstance = {
  elements: () => StripeElements
  confirmCardPayment: (clientSecret: string, data: { payment_method: { card: StripeCardElement } }) => Promise<{ error?: { message?: string }; paymentIntent?: { status?: string } }>
}

interface Window {
  Stripe?: (publishableKey: string) => StripeInstance
}
