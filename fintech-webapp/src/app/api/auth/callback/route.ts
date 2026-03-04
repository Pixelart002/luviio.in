import { createClient } from '@/lib/supabase/server'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const requestUrl = new URL(request.url)
  const code = requestUrl.searchParams.get('code')
  const origin = requestUrl.origin

  if (code) {
    const supabase = createClient()
    
    // Exchange the auth code for a session.
    // Supabase SSR automatically validates the state cookie (CSRF Check)
    // and sets the HttpOnly session cookie in the browser (Step 6, 7, 8)
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    
    if (!error) {
      return NextResponse.redirect(`${origin}/dashboard`)
    }
  }

  // Return to login if error or no code
  return NextResponse.redirect(`${origin}/login?error=Authentication%20Failed`)
}