# Vercel Environment Variables Setup Guide

## Quick Setup (3 minutes)

Follow these steps to add your Supabase credentials to your Vercel project.

### Step 1: Get Your Supabase Keys

1. Go to your Supabase dashboard: https://supabase.com/dashboard
2. Select your project: **enqcujmzxtrbfkaungpm**
3. Click **Settings** → **API** in the left sidebar
4. You'll see three keys:
   - **Project URL**: `https://enqcujmzxtrbfkaungpm.supabase.co` ✓ (Already configured)
   - **anon/public key**: Copy this → will be `SB_KEY`
   - **service_role/secret key**: Copy this → will be `SB_SERVICE_ROLE_KEY`

⚠️ **IMPORTANT**: Keep the `service_role/secret key` private! Never expose it in frontend code.

### Step 2: Add to Vercel Environment Variables

#### Option A: Via v0 Sidebar (Fastest)
1. In v0 chat, click the **Vars** section in the left sidebar
2. Click **+ Add Variable**
3. Add these variables:

```
Name: SB_URL
Value: https://enqcujmzxtrbfkaungpm.supabase.co

Name: SB_KEY
Value: [Your anon/public key from Supabase]

Name: SB_SERVICE_ROLE_KEY
Value: [Your service_role/secret key from Supabase]
```

4. Click **Save**

#### Option B: Via Vercel Dashboard (Alternative)
1. Go to your Vercel project: https://vercel.com/dashboard
2. Click your **LUVIIO** project
3. Go to **Settings** → **Environment Variables**
4. Add the same three variables above
5. Click **Deploy** to apply changes

### Step 3: Verify Setup

Once added, your OAuth system will automatically:
- Exchange authorization codes securely
- Store sessions with HTTPOnly cookies
- Manage user profiles
- Handle token refresh

### Environment Variable Reference

| Variable | Value | Where to Get |
|----------|-------|--------------|
| `SB_URL` | `https://enqcujmzxtrbfkaungpm.supabase.co` | Supabase → Settings → API (Project URL) |
| `SB_KEY` | Your anon/public key | Supabase → Settings → API (anon/public) |
| `SB_SERVICE_ROLE_KEY` | Your service_role key | Supabase → Settings → API (service_role) |

### Troubleshooting

**❌ "Missing SB_KEY" error?**
- Make sure the variable is named exactly `SB_KEY` (case-sensitive)
- Redeploy after adding the variable
- Clear your browser cache

**❌ "Supabase unreachable" error?**
- Verify the URL is correct: `https://enqcujmzxtrbfkaungpm.supabase.co`
- Check if your Supabase project is active
- Check your internet connection

**❌ "Invalid credentials" error?**
- Double-check you copied the entire key (no spaces)
- Make sure you used the correct `service_role` key (not the public key)
- Regenerate keys if needed in Supabase Settings

### What Happens Next?

Once your environment variables are set:

1. **OAuth Callback** (`/api/auth/callback`)
   - Securely exchanges auth codes for tokens
   - Returns HTTPOnly cookies (XSS-safe)
   - Redirects to dashboard or onboarding

2. **Email/Password Login** (`/api/auth/flow`)
   - Creates user accounts
   - Manages login sessions
   - Handles password resets

3. **Profile Management**
   - Creates user profiles on first login
   - Routes new users to onboarding
   - Routes returning users to dashboard

### Security Notes

✅ **HTTPOnly Cookies**: Tokens stored in secure, XSS-proof cookies
✅ **Server-Side Verification**: All tokens verified on backend
✅ **Token Expiration**: Access tokens expire after 1 hour
✅ **Refresh Tokens**: Refresh tokens expire after 30 days
✅ **CSRF Protection**: SameSite=Lax prevents CSRF attacks
✅ **RLS Policies**: Database enforces row-level security

### Need Help?

- **v0 Vars Section**: Click the blue "Vars" button in the left sidebar
- **Vercel Dashboard**: https://vercel.com/dashboard → Your Project → Settings
- **Supabase Dashboard**: https://supabase.com/dashboard → Your Project → Settings → API

---

**You're all set!** Your OAuth system is now configured and ready to authenticate users securely. 🎉
