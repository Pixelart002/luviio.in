# Authentication System - Architecture Diagrams

## 1. OAuth 2.0 with PKCE Flow

```
┌──────────────┐
│   Browser    │
│   (Client)   │
└──────────────┘
        │
        │ 1. User clicks "Login with Google"
        ↓
┌──────────────────────────────────────────────────────────────┐
│ GET /api/login?provider=google                               │
├──────────────────────────────────────────────────────────────┤
│ Server Actions:                                              │
│ • Generate PKCE verifier (64 bytes random)                  │
│ • Calculate code_challenge = SHA256(verifier)               │
│ • Store verifier in encrypted session                       │
│ • Create Session Cookie (luviio_session)                    │
│ • Redirect to Google OAuth                                  │
└──────────────────────────────────────────────────────────────┘
        │
        │ 2. Redirect to Google
        ↓
┌──────────────────────────────────────────────────────────────┐
│ Google OAuth Consent Page                                    │
├──────────────────────────────────────────────────────────────┤
│ https://accounts.google.com/o/oauth2/v2/auth?               │
│   client_id=...&                                             │
│   redirect_uri=https://luviio.in/api/auth/callback&        │
│   code_challenge=SHA256(verifier)&                          │
│   code_challenge_method=S256&                               │
│   scope=openid+email+profile                                │
└──────────────────────────────────────────────────────────────┘
        │
        │ 3. User approves consent
        ↓
┌──────────────┐
│   Browser    │ ← Google redirects with authorization code
│   + Session  │
│   + Code     │
└──────────────┘
        │
        │ 4. GET /api/auth/callback?code=AUTH_CODE
        ↓
┌──────────────────────────────────────────────────────────────┐
│ OAuth Callback Handler                                       │
├──────────────────────────────────────────────────────────────┤
│ Server Actions:                                              │
│ • Retrieve code_verifier from session                       │
│ • Exchange code + code_verifier for tokens                  │
│   POST to Supabase /auth/v1/token                           │
│ • ✓ PKCE validation (code_verifier must match verifier)    │
│ • Receive: access_token, refresh_token, user_data          │
│ • Check if user profile exists in database                  │
│ • Create profile if new user (onboarded=false)              │
│ • Delete session code_verifier (cleanup)                    │
│ • Set secure cookies:                                       │
│   - sb-access-token (HttpOnly, Secure, SameSite=Lax)       │
│   - sb-refresh-token (HttpOnly, Secure, SameSite=Lax)      │
│ • Redirect to /dashboard or /onboarding                     │
└──────────────────────────────────────────────────────────────┘
        │
        │ 5. Redirect to next page
        ↓
┌──────────────────────────────────────────────────────────────┐
│ Dashboard / Onboarding Page                                  │
├──────────────────────────────────────────────────────────────┤
│ User authenticated! ✓                                         │
│ Cookies set: sb-access-token, sb-refresh-token              │
│ Session cleaned up (verifier deleted)                       │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Request Authentication Flow

```
┌──────────────────────┐
│  Authenticated       │
│  User Session        │
└──────────────────────┘
        │
        │ Request to protected endpoint
        ↓
┌──────────────────────────────────────────────────────────────┐
│ GET /api/user/profile                                        │
│ Cookie: sb-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI...   │
├──────────────────────────────────────────────────────────────┤
│ Server Validation:                                           │
│                                                              │
│ 1. Extract access_token from cookies                        │
│    if (!access_token):                                      │
│       return 401 Unauthorized                               │
│                                                              │
│ 2. Verify token with Supabase                               │
│    POST to /auth/v1/user with Bearer token                  │
│    if (status != 200):                                      │
│       return 401 Invalid token                              │
│                                                              │
│ 3. Get user_id from token payload                           │
│    user_id = token.claims['sub']                            │
│                                                              │
│ 4. Fetch user profile from database                         │
│    SELECT * FROM profiles WHERE id = user_id               │
│    (RLS policy: auth.uid() = id)                           │
│                                                              │
│ 5. Return user data + profile                               │
│    {                                                         │
│      "success": true,                                        │
│      "user": { ... },                                       │
│      "profile": { ... }                                     │
│    }                                                         │
└──────────────────────────────────────────────────────────────┘
        │
        ↓
    Response sent to client with user data
```

---

## 3. Token Lifecycle

```
Authentication Token Timeline
═══════════════════════════════════════════════════════════════

LOGIN EVENT (T=0)
├─ Generate PKCE verifier
├─ User logs in with Google
├─ Exchange code for tokens
└─ Set cookies

ACTIVE SESSION (T=0 to T=3600)
├─ Access Token: Valid ✓
│  └─ Expires in: 1 hour (3600 seconds)
├─ Refresh Token: Valid ✓
│  └─ Expires in: 30 days (2592000 seconds)
└─ Can access dashboard & APIs

TOKEN EXPIRY (T=3600)
├─ Access Token: Expired ✗
├─ Refresh Token: Still valid ✓
├─ API returns 401 Unauthorized
├─ Client detects 401, submits refresh request
└─ Server exchanges refresh_token for new access_token

CONTINUED SESSION (T=3600 to T=2592000)
├─ New Access Token: Valid ✓
├─ Refresh Token: Still valid ✓ (or rotated)
└─ Can continue accessing resources

LONG EXPIRY (T=2592000)
├─ Access Token: Expired ✗
├─ Refresh Token: Expired ✗
├─ APIs return 401 Unauthorized
├─ Refresh request fails
└─ User must re-login (new PKCE flow)

RE-AUTHENTICATION
└─ Start OAuth flow again (back to LOGIN EVENT)
```

---

## 4. Database Schema & Access Control

```
┌─────────────────────────────────────────────────────────────┐
│ Supabase Auth (Built-in)                                    │
├─────────────────────────────────────────────────────────────┤
│ auth.users                                                   │
│ ├─ id (UUID, PK)          → User identifier                 │
│ ├─ email (TEXT)           → Login email                     │
│ ├─ encrypted_password     → Password hash (if email/pwd)   │
│ ├─ app_metadata           → Provider info (google, github) │
│ ├─ created_at             → Signup timestamp                │
│ └─ updated_at             → Last update timestamp           │
└─────────────────────────────────────────────────────────────┘
        │
        │ Referenced by Foreign Key
        ↓
┌─────────────────────────────────────────────────────────────┐
│ Custom Tables (Profiles)                                    │
├─────────────────────────────────────────────────────────────┤
│ profiles                                                     │
│ ├─ id (UUID, PK, FK→auth.users)  → User reference           │
│ ├─ email (TEXT)                   → Denormalized for search │
│ ├─ full_name (TEXT)               → Display name            │
│ ├─ avatar_url (TEXT)              → Profile picture         │
│ ├─ bio (TEXT)                     → User biography          │
│ ├─ onboarded (BOOLEAN)            → Setup complete flag     │
│ ├─ created_at (TIMESTAMP)         → Profile creation        │
│ └─ updated_at (TIMESTAMP)         → Last update             │
│                                                              │
│ Row Level Security (RLS) Policies:                          │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ Policy 1: VIEW OWN PROFILE                             │ │
│ │ GRANT SELECT ON profiles                               │ │
│ │ WHERE auth.uid() = id                                  │ │
│ │                                                         │ │
│ │ Policy 2: UPDATE OWN PROFILE                           │ │
│ │ GRANT UPDATE ON profiles                               │ │
│ │ WHERE auth.uid() = id                                  │ │
│ │ ALLOWED FIELDS: full_name, avatar_url, bio, onboarded │ │
│ │                                                         │ │
│ │ Policy 3: INSERT NEW PROFILE                           │ │
│ │ GRANT INSERT ON profiles                               │ │
│ │ TO authenticated                                        │ │
│ └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Cookie Structure & Security

```
HTTP Response Headers
═══════════════════════════════════════════════════════════════

Set-Cookie: luviio_session=<encrypted-session-id>
├─ HttpOnly      ✓ (JavaScript can't access)
├─ Secure        ✓ (HTTPS only)
├─ SameSite=Lax  ✓ (CSRF protection)
├─ Path=/        → Sent with all requests
├─ Domain=.luviio.in → All subdomains
└─ Max-Age=600   → Expires in 10 minutes
    Purpose: Store PKCE verifier during OAuth flow

Set-Cookie: sb-access-token=<JWT>
├─ HttpOnly      ✓ (JavaScript can't access)
├─ Secure        ✓ (HTTPS only)
├─ SameSite=Lax  ✓ (CSRF protection)
├─ Path=/        → Sent with all requests
├─ Domain=.luviio.in → All subdomains
└─ Max-Age=3600  → Expires in 1 hour
    Purpose: API authentication for protected endpoints

Set-Cookie: sb-refresh-token=<JWT>
├─ HttpOnly      ✓ (JavaScript can't access)
├─ Secure        ✓ (HTTPS only)
├─ SameSite=Lax  ✓ (CSRF protection)
├─ Path=/        → Sent with all requests
├─ Domain=.luviio.in → All subdomains
└─ Max-Age=2592000 → Expires in 30 days
    Purpose: Token renewal when access token expires
```

---

## 6. Protected Route Access Control

```
User Requests /dashboard
        │
        ↓
┌──────────────────────────────┐
│ Route Handler:               │
│ GET /dashboard               │
└──────────────────────────────┘
        │
        ↓
┌──────────────────────────────────────────────┐
│ Check Access Token                           │
│ if (!request.cookies.get("sb-access-token")): │
└──────────────────────────────────────────────┘
        │
        ├─ NO TOKEN
        │   ↓
        │  ┌──────────────────────────────────┐
        │  │ 302 Redirect to /login           │
        │  │ Location: /login?redirect=/dashboard
        │  └──────────────────────────────────┘
        │
        ├─ TOKEN INVALID
        │   ↓
        │  ┌──────────────────────────────────┐
        │  │ Token verification fails         │
        │  │ 302 Redirect to /login           │
        │  └──────────────────────────────────┘
        │
        ├─ TOKEN VALID ✓
        │   ↓
        │  ┌──────────────────────────────────────┐
        │  │ Render dashboard.html                │
        │  │ Pass Supabase credentials to JS      │
        │  │ JS fetches user profile from API     │
        │  └──────────────────────────────────────┘
        │
        └─ TOKEN EXPIRED
            ↓
           ┌──────────────────────────────────┐
           │ API endpoint returns 401          │
           │ Client JavaScript catches 401     │
           │ Redirects to /login               │
           └──────────────────────────────────┘
```

---

## 7. Data Flow - Dashboard Page Load

```
Browser: GET /dashboard
        │
        ├─ With Cookie: sb-access-token
        │
        ↓
Server checks token
        │
        ├─ Valid → Send dashboard.html
        │
        ↓
┌─────────────────────────────────────┐
│ Browser Loads dashboard.html        │
│ JavaScript Executes:                │
│ 1. fetch("/api/user/profile")       │
│    Sends request WITH cookies       │
└─────────────────────────────────────┘
        │
        ↓
┌──────────────────────────────────────────────┐
│ API Endpoint: GET /api/user/profile          │
│ 1. Validate access_token from cookie         │
│ 2. Query Supabase auth (who is this token?)  │
│ 3. Get user_id from token                    │
│ 4. Query database: SELECT * FROM profiles    │
│    WHERE id = user_id (RLS applies)          │
│ 5. Return { user, profile }                  │
└──────────────────────────────────────────────┘
        │
        ↓
┌─────────────────────────────────────┐
│ JavaScript Updates DOM              │
│ - Set user email                    │
│ - Show profile name                 │
│ - Display avatar initials           │
│ - Show member since date            │
│ - Display onboarding status         │
│ - Enable profile edit               │
└─────────────────────────────────────┘
        │
        ↓
Dashboard fully rendered with user data
```

---

## 8. Attack Prevention Matrix

```
Attack Type                 │ Prevention Method          │ Implementation
────────────────────────────┼────────────────────────────┼─────────────────────
XSS (JavaScript Token Theft)│ HttpOnly Cookies           │ Cookie flags set
CSRF (Forged Requests)      │ SameSite=Lax               │ Cookie flag
Authorization Code          │ PKCE (code_verifier)       │ Verifier stored
Interception                │ Server-side exchange       │ in encrypted session
                            │                            │
Session Fixation            │ New session after OAuth    │ Session cleanup
                            │                            │ after code exchange
                            │                            │
Token Exposure in URL       │ Cookies not in URL         │ Passed via Set-Cookie
                            │                            │ header
                            │                            │
Unencrypted Transport       │ HTTPS-only flag            │ Secure flag set
                            │                            │
Token Reuse                 │ Signed JWTs with exp       │ Supabase token format
                            │                            │
Unauthorized Access         │ Row-Level Security (RLS)   │ Database policies
                            │ Token validation per req   │ API checks token
                            │                            │
Refresh Token Abuse         │ Limited lifetime (30 days) │ Max-Age=2592000
                            │ HttpOnly storage           │
```

---

## 9. Error Handling Flow

```
User Requests Protected Resource
        │
        ↓
┌───────────────────────────────┐
│ Check Authentication           │
│ if not authenticated:          │
│   return 401 Unauthorized      │
└───────────────────────────────┘
        │
        ├─ No Token
        │   ↓
        │  Return 401
        │   ↓
        │  Client redirects to /login
        │
        ├─ Invalid Token
        │   ↓
        │  Validate with Supabase
        │   ↓
        │  Returns 401
        │   ↓
        │  Client redirects to /login
        │
        ├─ Expired Token
        │   ↓
        │  Try refresh endpoint
        │   ↓
        │  Get new access token
        │   ↓
        │  Retry request
        │   ↓
        │  Success (new token valid)
        │
        └─ Valid Token
            ↓
           Access granted
            ↓
           Return resource
```

---

## 10. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Vercel (Frontend + Backend)                                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ FastAPI Application (api/main.py)                      │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ Routes:                                                 │ │
│  │ • GET /api/login                                        │ │
│  │ • GET /api/auth/callback                               │ │
│  │ • GET /api/user/profile                                │ │
│  │ • POST /api/user/profile/update                        │ │
│  │ • GET /api/auth/logout                                 │ │
│  │ • GET /dashboard                                        │ │
│  │ • GET /login, /signup, /onboarding                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Environment Variables (from Vercel):                        │
│  • SESSION_SECRET (32+ chars)                               │
│  • SB_URL (Supabase URL)                                    │
│  • SB_KEY (Anon key)                                        │
│  • SB_SERVICE_ROLE_KEY (Service role)                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
        │
        │ API calls over HTTPS
        │ (OAuth redirects, token exchange)
        │
        ↓
┌─────────────────────────────────────────────────────────────┐
│ Supabase (Database + Auth)                                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Authentication Service:                                    │
│  • /auth/v1/authorize (OAuth redirect)                      │
│  • /auth/v1/token (code exchange)                           │
│  • /auth/v1/user (token verification)                       │
│                                                              │
│  Database:                                                   │
│  • auth.users (Supabase managed)                            │
│  • profiles (Custom table with RLS)                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
        │
        │ External provider redirects
        │
        ↓
┌─────────────────────────────────────────────────────────────┐
│ OAuth Provider (Google, GitHub, etc.)                        │
├─────────────────────────────────────────────────────────────┤
│ • Consent page                                               │
│ • Authorization code generation                              │
│ • User data (email, profile, etc.)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Summary

This architecture provides:
- ✅ Secure OAuth 2.0 with PKCE
- ✅ Server-side token exchange
- ✅ HttpOnly cookie storage
- ✅ Session management for PKCE verifier
- ✅ Protected routes with token validation
- ✅ Row-Level Security for user data
- ✅ Comprehensive error handling
- ✅ Production-ready deployment

All components work together to create a secure, scalable authentication system.
