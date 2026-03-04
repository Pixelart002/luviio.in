import { createClient } from '@/lib/supabase/server'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const supabase = createClient()
  const origin = process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: `${origin}/api/auth/callback`, // Callback route jahan Google bhejega
      queryParams: {
        access_type: 'offline',
        prompt: 'consent',
      },
    },
  })

  if (error) {
    return NextResponse.redirect(`${origin}/login?error=Could not authenticate`)
  }

  // Google ke auth URL par redirect (Isme state token include hota hai CSRF ke liye)
  return NextResponse.redirect(data.url)
}