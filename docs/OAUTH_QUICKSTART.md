# OAuth 2.0 Quick Start Guide

## 60-Second Setup

### 1. Add Environment Variables

```env
# .env (local) or Vercel → Settings → Environment Variables
SB_URL=https://enqcujmzxtrbfkaungpm.supabase.co
SB_KEY=your-anon-key
SB_SERVICE_ROLE_KEY=your-service-role-key
```

### 2. Create Profiles Table

Go to **Supabase Dashboard → SQL Editor** and run:

```sql
create table profiles (
  id uuid primary key references auth.users on delete cascade,
  email text unique not null,
  onboarded boolean default false,
  created_at timestamp default now()
);

alter table profiles enable row level security;

create policy "Users can read own profile"
  on profiles for select using (auth.uid() = id);
  
create policy "Users can update own profile"
  on profiles for update using (auth.uid() = id);
```

### 3. Enable OAuth Providers

**In Supabase Dashboard:**
1. Go to **Authentication → Providers**
2. Enable **Google** and **GitHub**
3. Add your credentials (see full guide for details)

### 4. Test It

```bash
cd api
uvicorn main:app --reload
```

Visit: `http://localhost:8000/login`

Click **"Google"** or **"GitHub"** → Authenticate → Should redirect to `/onboarding` ✅

---

## What Happens Behind the Scenes?

```
1. User clicks "Sign in with Google"
   ↓
2. Frontend redirects to Supabase OAuth URL (not shown to user)
   ↓
3. Google redirects back to /api/auth/callback?code=XXX
   ↓
4. Backend exchanges code for tokens (SECURE - not exposed to JS)
   ↓
5. Backend creates user profile if new
   ↓
6. Backend sets HTTPOnly cookies with tokens
   ↓
7. Backend redirects to /onboarding or /dashboard
   ↓
8. Frontend has secure session (tokens in HTTPOnly cookies)
```

---

## Code Architecture

### FastAPI Routes (`api/routes/auth.py`)

```python
@router.get("/auth/callback")
async def oauth_callback(...):
    """
    Handles OAuth redirect with secure token exchange.
    - Exchanges code for tokens (server-side)
    - Creates user profile if new (State A)
    - Checks onboarding status (State B/C)
    - Sets HTTPOnly cookies
    - Redirects to /onboarding or /dashboard
    """

@router.post("/auth/flow")
async def auth_flow_manual(...):
    """
    Handles email/password signup and login.
    - Validates credentials
    - Creates user on signup
    - Returns session data on login
    """

@router.get("/auth/logout")
async def logout(...):
    """Clears cookies and redirects to login"""

@router.get("/auth/status")
async def auth_status(...):
    """Returns current user info if authenticated"""
```

### OAuth Client Library (`api/utils/oauth_client.py`)

```python
class SupabaseOAuthClient:
    """
    Reusable OAuth client with methods:
    - exchange_authorization_code()      # OAuth code → tokens
    - email_password_signup()            # Create account
    - email_password_login()             # Sign in
    - verify_token()                     # Check if token valid
    - refresh_session()                  # Refresh expired token
    - get_or_create_profile()            # Profile management
    """
```

---

## Frontend Usage

### Login/Signup Page (`templates/app/auth/login.html`)

```html
<!-- OAuth Buttons (redirect to /api/auth/callback) -->
<button onclick="oauthLogin('google')">Sign in with Google</button>
<button onclick="oauthLogin('github')">Sign in with GitHub</button>

<!-- Email/Password Form (posts to /api/auth/flow) -->
<form id="authForm">
  <input type="email" id="email">
  <input type="password" id="password">
  <button type="submit">Sign In</button>
</form>
```

```javascript
async function oauthLogin(provider) {
  // Supabase client initiates OAuth flow
  // User gets redirected to provider
  // Provider redirects to /api/auth/callback
  // Backend handles everything securely
}

document.getElementById('authForm').addEventListener('submit', async (e) => {
  // POST to /api/auth/flow with email/password
  // Backend creates/verifies user
  // Returns next URL (onboarding or dashboard)
  // Frontend redirects
});
```

---

## 3-State Logic (Automatic Routing)

### After OAuth or Email/Password Login:

**State A - New User:**
```
✗ Profile doesn't exist
↓
✓ Create profile (onboarded=false)
↓
→ Redirect to /onboarding
```

**State B - Incomplete:**
```
✓ Profile exists
✗ profile.onboarded = false
↓
→ Redirect to /onboarding
```

**State C - Complete:**
```
✓ Profile exists
✓ profile.onboarded = true
↓
→ Redirect to /dashboard
```

---

## Using the OAuth Client

```python
from api.utils.oauth_client import SupabaseOAuthClient

# Initialize
client = SupabaseOAuthClient()

# OAuth Code Exchange
result = await client.exchange_authorization_code(code)
# Returns: {
#   "success": True,
#   "access_token": "...",
#   "refresh_token": "...",
#   "user": {"id": "...", "email": "..."}
# }

# Get or Create Profile
success, profile = await client.get_or_create_profile(user_id, email)
# Returns: (True, {"id": "...", "email": "...", "onboarded": false})

# Get Next URL
next_url = client.get_next_redirect_url(profile["onboarded"])
# Returns: "/dashboard" or "/onboarding"
```

---

## Testing Checklist

- [ ] Environment variables set (SB_URL, SB_KEY, SB_SERVICE_ROLE_KEY)
- [ ] Profiles table created in Supabase
- [ ] RLS policies enabled
- [ ] OAuth providers configured (Google/GitHub)
- [ ] Can click "Sign in with Google" → redirects to provider
- [ ] After auth, redirects to `/onboarding` (first time)
- [ ] Cookies set: `sb-access-token` and `sb-refresh-token`
- [ ] `/api/auth/status` returns authenticated user
- [ ] Can logout → redirects to login

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Missing env vars" warning | Add SB_URL, SB_KEY, SB_SERVICE_ROLE_KEY to .env |
| OAuth buttons don't work | Check providers enabled in Supabase, credentials added |
| Redirect loop | Clear cookies, check /api/auth/callback logs |
| Profile not created | Check `profiles` table exists, RLS policies correct |
| Can't login after signup | Check confirmation email, user account in Supabase |

---

## Security Summary

✅ **Authorization Code Flow (PKCE)** - Code never in JS
✅ **HTTPOnly Cookies** - Tokens can't be stolen via XSS
✅ **Secure Flag** - Cookies sent only over HTTPS
✅ **SameSite=Lax** - CSRF protection
✅ **Token Expiration** - 1 hour for access, 30 days for refresh

---

## Next Steps

1. **Onboarding Page** - `/api/onboarding` → Complete user profile
2. **Dashboard** - `/api/dashboard` → Main app
3. **Protected Routes** - Check `sb-access-token` cookie before rendering
4. **Profile Updates** - Use `/api/auth/status` to get current user

---

## Resources

- Full setup guide: `docs/OAUTH_SETUP.md`
- Supabase OAuth docs: https://supabase.com/docs/guides/auth
- OAuth 2.0 spec: https://tools.ietf.org/html/rfc6749
