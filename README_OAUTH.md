# OAuth 2.0 Authentication System - Quick Start

## 🚀 What's Included

This is a **production-ready OAuth 2.0 authentication system** for FastAPI + Supabase with comprehensive error handling and security best practices.

### ✨ Features

- ✅ **OAuth 2.0 Authorization Code Flow** - Google & GitHub support
- ✅ **Email/Password Authentication** - Signup & login with validation
- ✅ **Server-Side Token Exchange** - Secure, not exposed to frontend
- ✅ **HTTPOnly Secure Cookies** - XSS-safe token storage
- ✅ **3-State User Logic** - Automatic routing (New → Incomplete → Complete)
- ✅ **Jinja2 Macros** - Reusable, DRY templates
- ✅ **Error Handling** - Network, validation, OAuth provider errors
- ✅ **Production Ready** - Logging, timeouts, input validation

---

## 📁 Files Overview

### Core Backend
- **`api/routes/auth.py`** - OAuth callback, email auth, profile logic
- **`api/main.py`** - FastAPI app, environment validation, route mounting

### Frontend Templates
- **`api/templates/macros/auth_macros.html`** - Reusable input fields, buttons
- **`api/templates/app/auth/login.html`** - Login with OAuth & email/password
- **`api/templates/app/auth/signup.html`** - Signup with validation

### Documentation
- **`OAUTH_IMPLEMENTATION.md`** - Detailed architecture & security
- **`SETUP_CHECKLIST.md`** - Step-by-step setup instructions
- **`FLOW_EXAMPLES.md`** - Request/response examples for all flows
- **`.env.example`** - Environment variables template

---

## 🔐 Security Highlights

### HTTPOnly Cookies (Best Practice)
```python
response.set_cookie(
    key="sb-access-token",
    value=access_token,
    httponly=True,    # ✅ Not accessible to JavaScript
    secure=True,      # ✅ HTTPS only
    samesite="lax"    # ✅ CSRF protection
)
```

### PKCE OAuth Flow
- Authorization Code Exchange (not implicit)
- No tokens in URL fragments (secure)
- Server-side token handling

### Input Validation
- Email regex validation
- Password length minimum (6 chars)
- Sanitized JSON input
- Request timeout handling

---

## 🔄 3-State User Logic

```
┌─────────────────────────────────────────────────┐
│           User Onboarding Flow                  │
└─────────────────────────────────────────────────┘

STATE A: New User
├─ OAuth/Email signup
├─ No profile exists
├─ Backend creates profile (onboarded=False)
└─ Redirect → /onboarding

STATE B: Returning but Incomplete
├─ User logs in
├─ Profile exists
├─ onboarded = False
└─ Redirect → /onboarding

STATE C: Returning and Complete
├─ User logs in
├─ Profile exists
├─ onboarded = True
└─ Redirect → /dashboard
```

---

## 🚀 Quick Setup

### 1. Add Environment Variables (Vercel)

```bash
SB_URL=https://enqcujmzxtrbfkaungpm.supabase.co
SB_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SB_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 2. Create Database Table (Supabase SQL)

```sql
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    onboarded BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
```

### 3. Configure OAuth Providers

#### Google
1. [Google Cloud Console](https://console.cloud.google.com) → Create OAuth App
2. Add redirects: 
   - `https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback`
   - `https://your-domain.com/api/auth/callback`
3. Add credentials to Supabase

#### GitHub
1. [GitHub Settings → OAuth Apps](https://github.com/settings/apps)
2. Add redirects:
   - `https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback`
   - `https://your-domain.com/api/auth/callback`
3. Add credentials to Supabase

### 4. Deploy to Vercel

```bash
git push origin main
# Vercel automatically deploys
```

### 5. Test

1. Visit: `https://yourdomain.com/login`
2. Click "Google" or "GitHub"
3. Authorize
4. Should redirect to `/onboarding` (new) or `/dashboard` (existing)

---

## 📚 API Endpoints

### OAuth Callback
```
GET /api/auth/callback?code=...
```
- Exchanges authorization code for tokens
- Creates profile if new user
- Sets HTTPOnly cookies
- Redirects to `/onboarding` or `/dashboard`

### Email/Password Auth
```
POST /api/auth/flow
{
    "email": "user@example.com",
    "password": "password",
    "action": "login" or "signup"
}
```

### Logout
```
GET /api/auth/logout
```
- Clears cookies
- Redirects to `/login`

### Session Status (Optional)
```
GET /api/auth/status
```
- Returns authenticated status
- Returns user info if authenticated

---

## 🛠️ Frontend Integration

### OAuth Button
```javascript
async function oauthLogin(provider) {
    const { error } = await client.auth.signInWithOAuth({
        provider: provider,
        options: {
            redirectTo: window.location.origin + '/api/auth/callback'
        }
    });
}
```

### Manual Auth Form
```javascript
const res = await fetch('/api/auth/flow', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
        email: 'user@example.com',
        password: 'password',
        action: 'login'
    })
});

const data = await res.json();
if (data.next) {
    window.location.href = '/' + data.next;
}
```

---

## 🐛 Debugging

### Browser Console
```javascript
// See auth flow logs
[v0] Auth response: dashboard
[v0] OAuth error: { message: "..." }
[v0] Signup response: { next: "onboarding" }
```

### Vercel Logs
```
✓ OAuth successful for user@gmail.com
✓ Signup successful for newuser@example.com
❌ Token Exchange Failed: 401
⚠️ Missing environment variables
```

### Check Cookies
```javascript
// Browser DevTools → Application → Cookies
sb-access-token   // 1 hour
sb-refresh-token  // 30 days
```

---

## 🎯 Common Tasks

### Add Password Reset
```python
@router.post("/auth/reset-password")
async def reset_password(email: str):
    # Send password reset email via Supabase
    await client.auth.reset_password_for_email(email)
```

### Add Two-Factor Auth
1. Enable in Supabase → Authentication → MFA
2. Frontend prompts for OTP after password

### Add Rate Limiting
```python
from slowapi import Limiter

@app.post("/api/auth/flow")
@limiter.limit("5/minute")
async def auth_flow(request: Request):
    # Auth logic
```

### Add Email Confirmation Required
In Supabase → Authentication → Providers → Email:
- Enable "Confirm email"
- Users must verify email before login

---

## 📊 Database Schema

### profiles table
```
id (UUID)              - User ID from auth.users
email (VARCHAR)        - User email
onboarded (BOOLEAN)    - Profile completion status
created_at (TIMESTAMP) - Account creation date
updated_at (TIMESTAMP) - Last update date
```

### Example Row
```
id                              email                onboarded  created_at
12345678-1234-1234-1234-123... | user@gmail.com      | true      | 2024-02-13...
```

---

## ⚠️ Error Scenarios

### OAuth Provider Error
```
/login?error=access_denied&msg=User+cancelled
```

### Token Exchange Failed
```
/login?error=token_failed&msg=Invalid+code
```

### Invalid Credentials
```json
{
    "error": "Invalid login credentials"
}
```

### Email Already Exists
```json
{
    "error": "A user with this email address has already been registered"
}
```

---

## 📖 Detailed Documentation

- **`OAUTH_IMPLEMENTATION.md`** - Deep dive into architecture, security, logging
- **`SETUP_CHECKLIST.md`** - Step-by-step setup (Supabase, Vercel, testing)
- **`FLOW_EXAMPLES.md`** - Complete request/response examples for all flows

---

## ✅ Pre-Launch Checklist

- [ ] Supabase project created and configured
- [ ] OAuth providers (Google/GitHub) set up
- [ ] Environment variables added to Vercel
- [ ] Database profile table created
- [ ] RLS policies configured
- [ ] All three auth endpoints tested
- [ ] OAuth redirect URLs verified
- [ ] Email confirmation enabled/disabled as needed
- [ ] Error pages configured
- [ ] Production domain configured
- [ ] HTTPS enabled
- [ ] Logging monitored

---

## 🆘 Support

### Common Issues

**OAuth not working?**
- Check environment variables in Vercel
- Verify redirect URL matches in OAuth provider
- Clear browser cookies

**Profile not created?**
- Verify profiles table exists
- Check RLS policies
- Verify service role key

**Cookies not persisting?**
- Ensure HTTPS in production
- Check `secure=True` in settings
- Clear browser cookies

### Resources
- [Supabase Auth Docs](https://supabase.com/docs/guides/auth)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [OAuth 2.0 Spec](https://tools.ietf.org/html/rfc6749)
- [PKCE RFC](https://tools.ietf.org/html/rfc7636)

---

## 📝 License

This implementation is based on OAuth 2.0 specifications and Supabase best practices.

---

## 🎉 You're All Set!

Your production-ready OAuth authentication system is ready to deploy. Follow the **SETUP_CHECKLIST.md** for detailed step-by-step instructions.

**Happy authenticating! 🚀**
