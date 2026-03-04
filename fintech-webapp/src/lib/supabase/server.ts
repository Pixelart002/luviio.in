import { createServerClient, type CookieOptions } from '@supabase/ssr'
import { cookies } from 'next/headers'

export function createClient() {
  const cookieStore = cookies()

  return createServerClient(
    process.env.NEXT_PUBLIC_SB_URL!,
    process.env.NEXT_PUBLIC_SB_KEY!,
    {
      cookies: {
        get(name: string) {
          return cookieStore.get(name)?.value
        },
        set(name: string, value: string, options: CookieOptions) {
          try {
            cookieStore.set({ name, value, ...options })
          } catch (error) {
            // Server Component se call hone par handle karega
          }
        },
        remove(name: string, options: CookieOptions) {
          try {
            cookieStore.set({ name, value: '', ...options })
          } catch (error) {
            // Server Component se call hone par handle karega
          }
        },
      },
    }
  )
}

// Admin client using Service Role Key (Sirf critical backend API ke liye)
export function createAdminClient() {
  return createServerClient(
    process.env.NEXT_PUBLIC_SB_URL!,
    process.env.SB_SERVICE_ROLE_KEY!,
    {
      cookies: {
        get() { return null },
        set() {},
        remove() {}
      }
    }
  )
}