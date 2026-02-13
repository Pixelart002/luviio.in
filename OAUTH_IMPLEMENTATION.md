# OAuth 2.0 Authentication System - Implementation Guide

## Overview

This is a **production-ready OAuth 2.0 authentication system** for a FastAPI + Supabase application with full error handling, security best practices, and the **3-State User Logic** system.

**Key Features:**
- ✅ OAuth 2.0 Authorization Code Flow (Server-Side)
- ✅ Email/Password Authentication (Manual signup/login)
- ✅ HTTPOnly Secure Cookies (XSS-safe)
- ✅ 3-State User Flow (New → Incomplete → Complete)
- ✅ Comprehensive Error Handling
- ✅ Jinja2 Macro System (DRY Templates)
- ✅ Security Best Practices

---

## Architecture

### 1. **Backend Routes** (`api/routes/auth.py`)

#### `/api/auth/callback` - OAuth Callback Handler
**Purpose:** Exchange authorization code for session tokens (server-side)

```python
# OAuth Provider Flow
1. User clicks "Sign with Google/GitHub"
2. OAuth provider generates authorization code
3. Frontend redirects to /api/auth/callback?code=...
4. Backend exchanges code for access_token
5. Backend creates profile if new user
6. Backend sets HTTPOnly cookies
7. Backend redirects to /onboarding or /dashboard
```

**3-State Logic:**
- **State A (New User):** Create profile with `onboarded=False` → redirect `/onboarding`
- **State B (Incomplete):** Check profile status → redirect `/onboarding`
- **State C (Complete):** Check profile status → redirect `/dashboard`

#### `/api/auth/flow` - Manual Auth Endpoint
**Purpose:** Handle email/password signup and login

```json
POST /api/auth/flow
{
  "email": "user@example.com",
  "password": "password123",
  "action": "login" or "signup"
}

Response:
{
  "next": "dashboard",
  "session": { ... },
  "msg": "Check email for confirmation"
}
```

#### `/api/auth/logout` - Logout Handler
**Purpose:** Clear authentication cookies and redirect to login

```python
DELETE cookies:
- sb-access-token
- sb-refresh-token
```

#### `/api/auth/status` - Session Check (Optional)
**Purpose:** Verify if user has active session

```json
GET /api/auth/status

Response (authenticated):
{
  "authenticated": true,
  "user": {
    "id": "user-uuid",
    "email": "user@example.com"
  }
}
```

---

## Frontend Templates

### 1. **Macros** (`templates/macros/auth_macros.html`)

Reusable Jinja2 macros for consistent UI:

```jinja2
{# Input Field Macro #}
{{ forms.input_field('email', 'email', 'Email', 'ri-mail-line', autocomplete_type='email') }}

{# Submit Button Macro #}
{{ forms.submit_button('Sign In', 'submitBtn') }}

{# OAuth Buttons Macro #}
{{ forms.oauth_buttons() }}

{# Error/Success Alerts #}
{{ forms.error_alert('Error message') }}
{{ forms.success_alert('Success message') }}
```

### 2. **Login Page** (`templates/app/auth/login.html`)

- OAuth buttons (Google, GitHub)
- Email/Password form
- Toggle to signup
- Error/success alerts
- Auto-cleanup of URL parameters

### 3. **Signup Page** (`templates/app/auth/signup.html`)

- OAuth buttons (Google, GitHub)
- Email/Password form with validation
- Terms acceptance checkbox
- Email validation (regex)
- Success/error messaging

---

## Security Implementation

### 1. **HTTPOnly Cookies**
```python
response.set_cookie(
    key="sb-access-token",
    value=access_token,
    httponly=True,      # 🛡️ Not accessible to JavaScript
    secure=True,        # 🛡️ HTTPS only
    samesite="lax",     # 🛡️ CSRF protection
    max_age=3600        # 1 hour
)
```

**Why HTTPOnly?**
- Prevents XSS attacks (JavaScript cannot steal token)
- Automatically sent with requests
- Better than localStorage

### 2. **PKCE Flow** (Handled by Supabase SDK)
- Authorization Code Exchange (not implicit)
- No tokens in URL fragments
- Code verification for additional security

### 3. **Input Validation**
```python
# Backend validates:
- Email format (regex)
- Password length (minimum 6 chars)
- Action type (login/signup)
- Request format (JSON)

# Frontend validates:
- Email regex
- Password length
- Terms acceptance
- Required fields
```

### 4. **Error Handling**
```python
try:
    # OAuth/Auth logic
except httpx.TimeoutException:
    return error response (timeout)
except httpx.RequestError:
    return error response (network)
except Exception:
    return generic error response
```

---

## Environment Variables

**Required in Vercel Project Settings:**

```
SB_URL=https://your-project.supabase.co
SB_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  (Anon Key)
SB_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Startup Validation:**
```python
# main.py checks if all vars exist
if missing_vars:
    logger.warning("Missing environment variables")
    # App continues but auth won't work
```

---

## User Flow Diagrams

### OAuth Flow (Recommended)
```
User → Click "Google" → Frontend (Supabase SDK)
→ Google OAuth Provider → Google Auth → Authorization Code
→ Redirect to /api/auth/callback → Backend Token Exchange
→ Backend creates/checks profile → HTTPOnly Cookie
→ Backend redirects to /onboarding or /dashboard
```

### Email/Password Flow
```
User → Enter email/password → Frontend Form
→ POST /api/auth/flow → Backend Validation
→ Supabase Auth API → Token Response
→ Profile check (3-state logic) → Response with next URL
→ Frontend stores token/session → Redirect to /onboarding or /dashboard
```

### 3-State User Logic
```
New User (OAuth/Email):
  ├─ No profile exists
  └─ Create profile (onboarded=False)
  └─ Redirect /onboarding

Returning User (Incomplete):
  ├─ Profile exists
  ├─ onboarded = False
  └─ Redirect /onboarding

Returning User (Complete):
  ├─ Profile exists
  ├─ onboarded = True
  └─ Redirect /dashboard
```

---

## Database Schema

**Profiles Table:**
```sql
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id),
    email VARCHAR NOT NULL,
    onboarded BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

---

## Error Handling Examples

### OAuth Callback Errors
```
/login?error=no_code
/login?error=token_failed
/login?error=timeout
/login?error=network_error
/login?error=server_error
```

### Email/Password Errors
```json
{
  "error": "Invalid credentials"
}
{
  "error": "Email already exists"
}
{
  "error": "Password must be at least 6 characters"
}
{
  "error": "Server misconfigured"
}
```

---

## Logging

All auth operations are logged with descriptive messages:

```
✓ Creating new profile for user@example.com
✓ OAuth successful for user@example.com → Redirecting to /onboarding
✓ Signup successful for user@example.com
✓ Login successful for user@example.com → /dashboard
❌ Token Exchange Failed: 401 - Invalid code
⚠️ Missing environment variables: SB_URL, SB_KEY
```

---

## Testing

### Test OAuth Flow
1. Go to `/login`
2. Click "Google" or "GitHub" button
3. Authorize with OAuth provider
4. Should redirect to `/onboarding` (new) or `/dashboard` (existing)

### Test Email/Password
1. Go to `/signup`
2. Enter email and password
3. Check for validation errors
4. Submit form
5. Should redirect based on profile status

### Test 3-State Logic
1. Create new user (OAuth/Email)
2. Should go to `/onboarding`
3. After completing onboarding (`onboarded=true`)
4. Next login should go to `/dashboard`

---

## Debugging

**Enable console logs in browser:**
```javascript
// Logs in browser console
[v0] Auth response: dashboard
[v0] Signup response: { next: "onboarding" }
[v0] OAuth error: { message: "..." }
```

**Backend logs (Vercel):**
```
✓ OAuth successful for user@example.com → Redirecting to /onboarding
❌ Profile Check Failed: Connection timeout
⚠️ Missing Supabase environment variables
```

---

## Production Checklist

- [ ] All environment variables set in Vercel
- [ ] Supabase Auth configured (Google/GitHub providers)
- [ ] Profiles table created in Supabase
- [ ] Email confirmation enabled/disabled as needed
- [ ] Redirect URLs in OAuth providers match exactly
- [ ] HTTPS enabled (cookies require secure=True)
- [ ] Error pages configured
- [ ] Logging monitored in production
- [ ] Rate limiting considered for auth endpoints
- [ ] Privacy policy and terms links updated

---

## Common Issues

### Issue: "Server misconfigured"
**Solution:** Check environment variables in Vercel settings

### Issue: OAuth redirect loop
**Solution:** Ensure redirect URL in OAuth provider matches `/api/auth/callback`

### Issue: Cookies not persisting
**Solution:** Verify `secure=True` and HTTPS in production

### Issue: Profile not created
**Solution:** Check Supabase profiles table has correct RLS policies

---

## References

- [Supabase Auth Docs](https://supabase.com/docs/guides/auth)
- [OAuth 2.0 RFC](https://tools.ietf.org/html/rfc6749)
- [PKCE RFC](https://tools.ietf.org/html/rfc7636)
- [FastAPI Cookies](https://fastapi.tiangolo.com/advanced/response-cookies/)
- [HTTPOnly Cookies Security](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
