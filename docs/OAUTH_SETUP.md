# OAuth 2.0 Authentication System - Setup & Deployment Guide

## Overview

This document describes the complete OAuth 2.0 authentication system for LUVIIO using Supabase with **Authorization Code Flow (PKCE)** for maximum security.

### Key Features

✅ **Server-Side Token Exchange** - Authorization codes never exposed to frontend
✅ **3-State Logic** - Automatic routing for new users, incomplete, and complete profiles
✅ **HTTPOnly Secure Cookies** - XSS-proof session storage
✅ **Edge Function Support** - Scalable token exchange via Supabase Edge Functions
✅ **Python OAuth Client** - Reusable, production-ready client library
✅ **Error Handling** - Comprehensive error handling with fallback mechanisms

---

## Architecture

### Components

1. **FastAPI Backend** (`api/routes/auth.py`)
   - OAuth callback handler
   - Email/password authentication
   - Profile management
   - Session verification

2. **OAuth Client Library** (`api/utils/oauth_client.py`)
   - Token exchange (Authorization Code Flow)
   - Email/password authentication
   - Token refresh and verification
   - Profile operations

3. **Supabase Edge Function** (`supabase/functions/oauth-callback/main.py`)
   - Serverless token exchange
   - Can be deployed independently
   - Scales automatically

4. **Frontend Templates**
   - `login.html` - Login with OAuth and email/password
   - `signup.html` - Signup with OAuth and email/password
   - `auth_macros.html` - Reusable form components

### Authentication Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    OAuth 2.0 Flow (PKCE)                    │
└─────────────────────────────────────────────────────────────┘

User clicks "Sign in with Google"
        │
        ▼
Frontend redirects to Supabase OAuth provider
        │
        ▼
User approves on provider (Google/GitHub)
        │
        ▼
Provider redirects to /api/auth/callback?code=XXX
        │
        ▼
Backend exchanges code for tokens (secure, server-side)
        │
        ▼
Backend checks/creates user profile (3-State Logic)
        │
        ▼
Backend sets HTTPOnly cookies with tokens
        │
        ▼
Backend redirects to /onboarding or /dashboard
        │
        ▼
✅ User authenticated (tokens stored securely)
```

---

## 3-State Logic

The system automatically routes users based on their authentication state:

### State A: New Signup
```
New User Created → Profile doesn't exist
→ Create Profile (onboarded=False)
→ Redirect to /onboarding
```

### State B: Login - Incomplete
```
User Authenticates → Profile exists
→ Check profile.onboarded = False
→ Redirect to /onboarding
```

### State C: Login - Complete
```
User Authenticates → Profile exists
→ Check profile.onboarded = True
→ Redirect to /dashboard
```

---

## Local Development Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Add to `.env` or Vercel project settings:

```env
SB_URL=https://enqcujmzxtrbfkaungpm.supabase.co
SB_KEY=your-anon-key
SB_SERVICE_ROLE_KEY=your-service-role-key
```

### 3. Configure OAuth Providers

#### Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable Google+ API
4. Create OAuth 2.0 credentials (Web Application)
5. Add authorized redirect URIs:
   - `http://localhost:8000/api/auth/callback`
   - `https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback` (if using Edge Function)
   - `https://your-domain.com/api/auth/callback` (your production domain)
6. Copy Client ID and Secret
7. Go to Supabase Dashboard → Authentication → Providers → Google
8. Enable Google and paste credentials

#### GitHub OAuth

1. Go to GitHub Settings → Developer settings → OAuth Apps
2. Create New OAuth App
3. Set Authorization callback URL:
   - `https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback` (if using Edge Function)
   - `https://your-domain.com/api/auth/callback` (your production domain)
4. Copy Client ID and Secret
5. Go to Supabase Dashboard → Authentication → Providers → GitHub
6. Enable GitHub and paste credentials

### 4. Create Users Table

```sql
-- In Supabase SQL Editor
create table profiles (
  id uuid primary key references auth.users on delete cascade,
  email text unique not null,
  onboarded boolean default false,
  created_at timestamp default now(),
  updated_at timestamp default now()
);

-- Enable RLS (Row Level Security)
alter table profiles enable row level security;

-- Allow users to read their own profile
create policy "Users can read own profile"
  on profiles for select
  using (auth.uid() = id);

-- Allow users to update their own profile
create policy "Users can update own profile"
  on profiles for update
  using (auth.uid() = id);
```

### 5. Start Development Server

```bash
cd api && uvicorn main:app --reload
```

Visit: `http://localhost:8000/login`

---

## Deployment

### Option A: FastAPI + Vercel (Recommended)

1. Push code to GitHub
2. Connect repo to Vercel
3. Add environment variables in Vercel project settings
4. Deploy!

### Option B: Edge Function (Supabase)

1. Ensure Supabase CLI is installed:
   ```bash
   npm install -g supabase
   ```

2. Link your project:
   ```bash
   supabase link --project-ref your-project-ref
   ```

3. Deploy function:
   ```bash
   supabase functions deploy oauth-callback
   ```

4. Set function secrets:
   ```bash
   supabase secrets set --env-file .env.supabase
   ```

5. The function is now available at:
   ```
   https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback
   ```

---

## API Endpoints

### 1. OAuth Callback (Server-Side)
```
GET /api/auth/callback?code=XXX&error=optional
```
**Response:** Redirect to `/onboarding` or `/dashboard` with HTTPOnly cookies set

**Error Cases:**
- `?error=no_code` - Missing authorization code
- `?error=token_exchange_failed` - Code exchange failed
- `?error=invalid_token_response` - Invalid token response

### 2. Email/Password Authentication
```
POST /api/auth/flow
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword",
  "action": "signup" | "login"
}
```

**Response:**
```json
{
  "success": true,
  "next": "onboarding" | "dashboard",
  "msg": "Signup successful! Check email for confirmation.",
  "session": {
    "access_token": "jwt...",
    "refresh_token": "jwt...",
    "expires_in": 3600,
    "user": { "id": "uuid", "email": "..." }
  }
}
```

### 3. Logout
```
GET /api/auth/logout
```
**Response:** Redirect to `/login`, cookies deleted

### 4. Auth Status Check
```
GET /api/auth/status
```

**Response (Authenticated):**
```json
{
  "authenticated": true,
  "user": {
    "id": "uuid",
    "email": "user@example.com"
  }
}
```

**Response (Not Authenticated):**
```json
{
  "authenticated": false
}
```

---

## Using the OAuth Client Library

### Standalone Usage

```python
from api.utils.oauth_client import SupabaseOAuthClient

# Initialize
client = SupabaseOAuthClient(
    supabase_url="https://your-project.supabase.co",
    supabase_key="your-anon-key",
    service_role_key="your-service-role-key"
)

# Exchange authorization code
result = await client.exchange_authorization_code("code_from_oauth_provider")
if result["success"]:
    print(f"Token: {result['access_token']}")
    print(f"User: {result['user']}")

# Email/Password signup
result = await client.email_password_signup("user@example.com", "password")

# Email/Password login
result = await client.email_password_login("user@example.com", "password")

# Verify token
result = await client.verify_token("access_token_from_cookie")

# Get or create profile
success, profile = await client.get_or_create_profile(user_id, email)

# Get redirect URL based on onboarding status
next_url = client.get_next_redirect_url(is_onboarded=True)  # Returns "/dashboard"
```

---

## Security Best Practices

### ✅ Implemented

1. **Authorization Code Flow (PKCE)** - Code never exposed to frontend
2. **HTTPOnly Cookies** - Tokens cannot be accessed via JavaScript (XSS-proof)
3. **Secure Flag** - Cookies sent only over HTTPS
4. **SameSite=Lax** - CSRF protection
5. **Token Expiration** - Access tokens expire in 1 hour
6. **Service Role Key** - Used only on backend for admin operations
7. **Input Validation** - Email format, password length checks
8. **Error Hiding** - Generic error messages to prevent user enumeration

### ⚠️ Additional Considerations

1. **HTTPS Only** - Always use HTTPS in production
2. **Rate Limiting** - Consider rate limiting auth endpoints
3. **2FA** - Add two-factor authentication for sensitive operations
4. **Session Management** - Implement token refresh logic
5. **Logging** - Monitor failed login attempts
6. **CORS** - Restrict CORS to trusted domains only

---

## Troubleshooting

### Problem: "Missing environment variables" warning

**Solution:** Add `SB_URL`, `SB_KEY`, and `SB_SERVICE_ROLE_KEY` to:
- Local: `.env` file
- Vercel: Project Settings → Environment Variables

### Problem: OAuth redirect not working

**Solution:** 
1. Check redirect URL matches provider settings exactly
2. Verify provider is enabled in Supabase Dashboard
3. Check browser console for errors
4. Test with `/api/auth/callback?code=test` (should redirect to login)

### Problem: "Supabase client unavailable"

**Solution:**
1. Verify Supabase URL is correct (no trailing slash)
2. Check API keys have correct permissions
3. Restart development server

### Problem: Tokens not persisting

**Solution:**
1. Check HTTPOnly cookies are being set (DevTools → Application → Cookies)
2. Verify domain matches (no localhost vs 127.0.0.1 mismatch)
3. Ensure HTTPS in production (secure flag requires HTTPS)

### Problem: Profile not created after signup

**Solution:**
1. Check `profiles` table exists in Supabase
2. Verify RLS policies allow inserts
3. Check service role key has table access
4. Look at server logs for error details

---

## Testing

### Test OAuth Flow Locally

1. Go to `http://localhost:8000/login`
2. Click "Google" or "GitHub" button
3. Authenticate with provider
4. Should redirect to `/onboarding` (first time) or `/dashboard` (returning user)
5. Check cookies in DevTools (should see `sb-access-token` and `sb-refresh-token`)

### Test Email/Password Flow

```javascript
// In browser console
fetch('/api/auth/flow', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({
    email: 'test@example.com',
    password: 'testpassword123',
    action: 'signup'
  })
})
.then(r => r.json())
.then(console.log)
```

### Check Token Validity

```javascript
fetch('/api/auth/status', { credentials: 'include' })
  .then(r => r.json())
  .then(console.log)
```

---

## Advanced: Custom OAuth Flow

### Implement Custom Provider

```python
# In your route handler
from api.utils.oauth_client import SupabaseOAuthClient

@router.post("/api/custom-auth")
async def custom_auth(request: Request):
    client = SupabaseOAuthClient()
    
    # Your custom logic here
    token_result = await client.exchange_authorization_code(code)
    
    if token_result["success"]:
        # Handle successful auth
        pass
    
    return JSONResponse(token_result)
```

---

## Monitoring & Logging

All auth operations are logged to stdout:

```
INFO | 2024-01-15 10:30:45 | AUTH-ENGINE | ✓ OAuth successful for user@example.com → /onboarding
INFO | 2024-01-15 10:31:12 | AUTH-ENGINE | ✓ Login successful: user@example.com
ERROR | 2024-01-15 10:32:00 | AUTH-ENGINE | ❌ Token Exchange Failed: 400 - invalid_code
```

Monitor these logs in:
- **Vercel:** Project Settings → Logs
- **Supabase:** Project Settings → Logs
- **Local:** Terminal output

---

## Support & Resources

- **Supabase Docs:** https://supabase.com/docs/guides/auth
- **OAuth 2.0 RFC:** https://tools.ietf.org/html/rfc6749
- **PKCE Flow:** https://tools.ietf.org/html/rfc7636
- **FastAPI Docs:** https://fastapi.tiangolo.com

---

## Changelog

- **v1.0.0** (Initial Release)
  - OAuth 2.0 Authorization Code Flow
  - Email/Password Authentication
  - 3-State Logic Implementation
  - Python OAuth Client Library
  - Supabase Edge Function Support
  - HTTPOnly Secure Cookies
  - Comprehensive Error Handling
