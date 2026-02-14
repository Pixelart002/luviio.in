# OAuth 2.0 Quick Reference Card

## Setup (Copy & Paste)

### 1. Environment Variables

```env
# .env or Vercel → Settings → Environment Variables
SB_URL=https://enqcujmzxtrbfkaungpm.supabase.co
SB_KEY=your-anon-key
SB_SERVICE_ROLE_KEY=your-service-role-key
```

### 2. Supabase SQL

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

### 3. OAuth Providers

1. **Google:** https://console.cloud.google.com
   - Create OAuth 2.0 credentials
   - Add redirect: `https://your-domain.com/api/auth/callback`

2. **GitHub:** https://github.com/settings/developers
   - Create OAuth App
   - Set callback: `https://your-domain.com/api/auth/callback`

3. **Supabase:** Dashboard → Authentication → Providers
   - Enable Google, add credentials
   - Enable GitHub, add credentials

### 4. Start Server

```bash
cd api
uvicorn main:app --reload
```

Visit: `http://localhost:8000/login`

---

## API Endpoints (Quick Reference)

### OAuth Callback
```
GET /api/auth/callback?code=XXX
Response: 302 redirect to /onboarding or /dashboard
```

### Email/Password Auth
```
POST /api/auth/flow
{
  "email": "user@example.com",
  "password": "password",
  "action": "login" | "signup"
}
```

### Logout
```
GET /api/auth/logout
Response: 302 redirect to /login
```

### Check Auth Status
```
GET /api/auth/status
Response: { "authenticated": true/false, "user": {...} }
```

---

## Code Snippets

### Frontend: OAuth Button
```javascript
async function oauthLogin(provider) {
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: provider,
    options: {
      redirectTo: window.location.origin + '/api/auth/callback'
    }
  });
  if (error) console.error(error);
}
```

### Frontend: Email/Password
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
if (data.next) window.location.href = '/' + data.next;
```

### Backend: Use OAuth Client
```python
from api.utils.oauth_client import SupabaseOAuthClient

client = SupabaseOAuthClient()

# Exchange OAuth code
result = await client.exchange_authorization_code(code)
token = result["access_token"]

# Get/create profile
success, profile = await client.get_or_create_profile(user_id, email)

# Get redirect URL
next_url = client.get_next_redirect_url(profile["onboarded"])
```

---

## Troubleshooting

| Problem | Command | Solution |
|---------|---------|----------|
| Missing env vars | `echo $SB_URL` | Add to .env, restart server |
| OAuth not working | Check `/api/auth/callback?code=test` | Verify provider config |
| Cookies not setting | DevTools → Application → Cookies | Check HTTPS, domain |
| Profile not created | Check Supabase logs | Verify RLS policies |
| Token invalid | Test `/api/auth/status` | Check if expired |

---

## File Structure

```
api/
├── main.py                          # FastAPI app
├── routes/
│   └── auth.py                      # OAuth & auth endpoints
└── utils/
    └── oauth_client.py              # OAuth client library (USE THIS!)

supabase/functions/oauth-callback/
├── main.py                          # Edge Function (optional)
└── pyproject.toml                   # Dependencies

templates/app/auth/
├── login.html                       # Login page
└── signup.html                      # Signup page

docs/
├── OAUTH_SETUP.md                   # Full guide
├── OAUTH_QUICKSTART.md              # Quick start
├── EDGE_FUNCTION_DEPLOYMENT.md      # Deploy to Edge Function
├── OAUTH_IMPLEMENTATION_SUMMARY.md  # What was built
└── OAUTH_QUICK_REFERENCE.md         # This file
```

---

## Environment Variables

| Variable | Example | Required |
|----------|---------|----------|
| SB_URL | `https://abc123.supabase.co` | ✅ Yes |
| SB_KEY | `eyJhbGc...` (anon key) | ✅ Yes |
| SB_SERVICE_ROLE_KEY | `eyJhbGc...` (service role) | ✅ Yes |

---

## Security Summary

✅ OAuth 2.0 Authorization Code Flow (PKCE)
✅ Server-side token exchange (not exposed to JS)
✅ HTTPOnly cookies (XSS-proof)
✅ Secure flag (HTTPS only)
✅ SameSite=Lax (CSRF protection)
✅ Token expiration (1 hour)
✅ Input validation
✅ Error message sanitization

---

## Testing Workflow

1. **OAuth Login**
   ```
   Click "Sign in with Google"
   → Authenticate
   → Redirected to /onboarding (first time)
   → Check cookies in DevTools
   ```

2. **Email/Password Signup**
   ```
   Click "Create one"
   → Enter email & password
   → Submit
   → Redirected to /onboarding
   ```

3. **Check Session**
   ```
   fetch('/api/auth/status', { credentials: 'include' })
     .then(r => r.json())
     .then(console.log)  // Should show authenticated: true
   ```

4. **Logout**
   ```
   Click "Logout" button
   → Redirected to /login
   → Cookies cleared
   ```

---

## Common Errors

```
❌ "Missing environment variables"
→ Add SB_URL, SB_KEY, SB_SERVICE_ROLE_KEY to .env

❌ "OAuth Provider Error: invalid_request"
→ Check redirect URL in provider settings matches exactly

❌ "token_exchange_failed"
→ Check provider credentials in Supabase

❌ "Profile not created"
→ Verify `profiles` table exists, RLS policies set

❌ "Cookies not persisting"
→ Check HTTPS is enabled, domain matches
```

---

## Performance Targets

| Operation | Target |
|-----------|--------|
| OAuth flow start to finish | <1 second |
| Token exchange | <300ms |
| Profile check | <150ms |
| Email/password auth | <400ms |

---

## Deployment Checklist

### Before Going Live

- [ ] Environment variables set in Vercel
- [ ] Profiles table created in Supabase
- [ ] OAuth providers configured with production URLs
- [ ] Tested OAuth flow end-to-end
- [ ] Tested email/password flow end-to-end
- [ ] Cookies setting correctly (verify in browser)
- [ ] Error handling working (test with bad code)
- [ ] Logs accessible (Vercel/Supabase dashboards)

### Going Live

```bash
# Push to main branch
git add .
git commit -m "feat: OAuth 2.0 authentication system"
git push origin main

# Vercel auto-deploys via GitHub integration
# Monitor: Vercel Dashboard → Deployments → Logs
```

---

## Monitoring

### View Logs

**Vercel:**
```bash
vercel logs api  # or use dashboard
```

**Supabase:**
- Dashboard → SQL Editor → Query → View recent queries
- Functions → oauth-callback → Logs (if using Edge Function)

### Key Metrics

- OAuth success rate
- Token exchange latency
- Profile creation rate
- Error frequency by type

---

## Next Steps

1. ✅ Copy env vars to .env
2. ✅ Create profiles table (copy SQL above)
3. ✅ Configure OAuth providers
4. ✅ Test OAuth flow
5. → Build `/onboarding` page
6. → Build `/dashboard` page
7. → Deploy to production

---

## Resources

| Resource | Link |
|----------|------|
| Full Setup | `/docs/OAUTH_SETUP.md` |
| Quick Start | `/docs/OAUTH_QUICKSTART.md` |
| Edge Function | `/docs/EDGE_FUNCTION_DEPLOYMENT.md` |
| Implementation | `/docs/OAUTH_IMPLEMENTATION_SUMMARY.md` |
| Supabase Docs | https://supabase.com/docs/guides/auth |
| OAuth 2.0 Spec | https://tools.ietf.org/html/rfc6749 |
| PKCE Spec | https://tools.ietf.org/html/rfc7636 |

---

## Support

Found an issue? Check:

1. **Logs:** Vercel → Logs, or terminal output
2. **Docs:** Read appropriate guide above
3. **Supabase Docs:** https://supabase.com/docs
4. **GitHub Issues:** https://github.com/supabase/supabase/issues

---

**Print this card and keep it handy!** 🚀
