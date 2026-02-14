# OAuth 2.0 Setup Checklist

## Phase 1: Supabase Configuration

### 1.1 Create Supabase Project
- [ ] Go to [supabase.com](https://supabase.com)
- [ ] Click "New Project"
- [ ] Select region (closest to users)
- [ ] Save project credentials

### 1.2 Get API Keys
- [ ] Go to Project Settings → API
- [ ] Copy **Project URL** → `SB_URL`
- [ ] Copy **Anon Key** → `SB_KEY`
- [ ] Copy **Service Role Key** → `SB_SERVICE_ROLE_KEY`

### 1.3 Create Profiles Table
In Supabase SQL Editor, run:

```sql
-- Create profiles table
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    onboarded BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Enable Row Level Security
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Create policy for users to view their own profile
CREATE POLICY "Users can view own profile" ON profiles
    FOR SELECT USING (auth.uid() = id);

-- Create policy for users to update own profile
CREATE POLICY "Users can update own profile" ON profiles
    FOR UPDATE USING (auth.uid() = id);
```

### 1.4 Configure OAuth Providers

#### Google OAuth
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project
3. Enable "Google+ API"
4. Create OAuth 2.0 Client (Web Application)
5. Add Authorized redirect URIs:
   - `https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback`
   - `https://your-domain.com/api/auth/callback` (production)
6. Copy Client ID and Client Secret
7. In Supabase:
   - Authentication → Providers → Google
   - Enable Google
   - Paste Client ID and Client Secret
   - Add redirect URL to your app domain

#### GitHub OAuth
1. Go to [GitHub Settings → Developer Settings → OAuth Apps](https://github.com/settings/apps)
2. Create New OAuth App
3. Set Authorization callback URL:
   - `https://your-project-id.supabase.co/auth/v1/callback`
4. Copy Client ID and Client Secret
5. In Supabase:
   - Authentication → Providers → GitHub
   - Enable GitHub
   - Paste Client ID and Client Secret
   - Add redirect URL to your app domain

---

## Phase 2: Vercel Deployment

### 2.1 Connect to Vercel
- [ ] Go to [vercel.com](https://vercel.com)
- [ ] Click "New Project"
- [ ] Import from Git (or upload code)
- [ ] Select repository

### 2.2 Add Environment Variables
In Vercel → Project Settings → Environment Variables:

```
SB_URL = https://your-project-id.supabase.co
SB_KEY = eyJhbGc...
SB_SERVICE_ROLE_KEY = eyJhbGc...
```

- [ ] Add `SB_URL`
- [ ] Add `SB_KEY` (Public, safe for frontend)
- [ ] Add `SB_SERVICE_ROLE_KEY` (Secret, server-only)

### 2.3 Configure Domains
- [ ] Add domain in Vercel
- [ ] Update OAuth redirect URIs:
  - `https://your-domain.com/api/auth/callback`

---

## Phase 3: Local Development

### 3.1 Clone Repository
```bash
git clone <your-repo-url>
cd luviio.in
```

### 3.2 Setup Environment
```bash
cp .env.example .env.local
# Edit .env.local and add your credentials
```

### 3.3 Install Dependencies
```bash
pip install -r requirements.txt
```

### 3.4 Run Locally
```bash
cd api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Access at: `http://localhost:8000`

### 3.5 Test OAuth Locally
**Important:** OAuth requires HTTPS or localhost

1. Go to `http://localhost:8000/login`
2. Click "Google" or "GitHub"
3. Authorize
4. Should redirect to `/onboarding` or `/dashboard`

---

## Phase 4: Database Setup

### 4.1 Verify Profiles Table
In Supabase:
- [ ] Go to SQL Editor
- [ ] Run: `SELECT * FROM profiles LIMIT 1;`
- [ ] Verify table structure

### 4.2 Test Profile Creation
1. Create a new account via signup
2. Check Supabase → profiles table
3. Verify `onboarded = false`

### 4.3 Test Profile Update
1. Complete onboarding
2. Check profiles table
3. Verify `onboarded = true`

---

## Phase 5: Production Deployment

### 5.1 Final Environment Variables Check
- [ ] All three Supabase keys in Vercel
- [ ] Keys are not in repository
- [ ] .env file in .gitignore

### 5.2 Domain Configuration
- [ ] Domain points to Vercel
- [ ] SSL certificate active
- [ ] OAuth redirect URIs updated to prod domain

### 5.3 Pre-Launch Tests
- [ ] Test OAuth with Google
- [ ] Test OAuth with GitHub
- [ ] Test email/password signup
- [ ] Test email/password login
- [ ] Test logout
- [ ] Test 3-state logic (new user → onboarding → dashboard)

### 5.4 Deploy
```bash
git push <branch>
# Vercel auto-deploys
```

### 5.5 Monitor
- [ ] Check Vercel logs for errors
- [ ] Monitor auth routes in Supabase
- [ ] Check email confirmations working

---

## Phase 6: Advanced Configuration (Optional)

### 6.1 Email Confirmation
In Supabase → Authentication → Providers → Email:
- [ ] Enable "Confirm email"
- [ ] Configure email templates

### 6.2 Rate Limiting
In FastAPI:
```python
# Add slowapi for rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/auth/flow")
@limiter.limit("5/minute")
async def auth_flow(request: Request):
    # Auth logic
```

### 6.3 Password Reset
Create endpoint:
```python
@router.post("/auth/reset-password")
async def reset_password(email: str):
    # Send reset email via Supabase
```

### 6.4 Two-Factor Authentication
Enable in Supabase → Authentication → Multi-factor Authentication

---

## Troubleshooting

### OAuth Not Working
1. Check environment variables in Vercel
2. Verify redirect URL matches exactly in OAuth provider
3. Check browser console for errors (F12)
4. Check Vercel logs

### Profile Not Created
1. Check profiles table exists
2. Verify RLS policies
3. Check Supabase service role key is correct

### Cookies Not Persisting
1. Ensure HTTPS in production
2. Check `secure=True` in cookie settings
3. Clear browser cookies and retry

### Email Confirmation Not Sent
1. Check Supabase email settings
2. Verify email templates
3. Check spam folder
4. Check Resend API (if configured)

---

## Support Resources

- [Supabase Auth Docs](https://supabase.com/docs/guides/auth)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [OAuth 2.0 Specification](https://tools.ietf.org/html/rfc6749)
- [Vercel Documentation](https://vercel.com/docs)
- [GitHub OAuth Documentation](https://docs.github.com/en/developers/apps/building-oauth-apps)
- [Google OAuth Documentation](https://developers.google.com/identity/protocols/oauth2)

---

## Completion Status

- [ ] Phase 1: Supabase Configuration
- [ ] Phase 2: Vercel Deployment
- [ ] Phase 3: Local Development
- [ ] Phase 4: Database Setup
- [ ] Phase 5: Production Deployment
- [ ] Phase 6: Advanced Configuration (Optional)

**All done? 🎉 Your OAuth system is ready for production!**
