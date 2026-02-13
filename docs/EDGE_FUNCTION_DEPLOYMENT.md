# Deploying OAuth to Supabase Edge Functions

This guide shows how to deploy the OAuth callback handler as a serverless Supabase Edge Function.

## Why Edge Functions?

✅ **Automatic Scaling** - Handles 1,000+ requests/second
✅ **Low Latency** - Closer to your users
✅ **Cost Effective** - Pay per invocation
✅ **No Server Management** - Fully managed by Supabase
✅ **Independent from FastAPI** - Can work alongside or replace backend

---

## Prerequisites

- Supabase project created
- [Supabase CLI installed](https://supabase.com/docs/guides/cli)
- OAuth providers configured (Google/GitHub)
- Profiles table created

---

## Step 1: Install Supabase CLI

```bash
npm install -g supabase
```

Verify installation:
```bash
supabase --version
```

---

## Step 2: Link Your Project

```bash
# From project root
supabase link --project-ref your-project-ref

# You'll be prompted to enter your Supabase password
```

Find your project ref in Supabase Dashboard → Settings → General → Project Ref

---

## Step 3: Create Function Secrets

Create a `.env.supabase` file:

```env
SUPABASE_URL=https://enqcujmzxtrbfkaungpm.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key
```

Push secrets to Supabase:

```bash
supabase secrets set --env-file .env.supabase
```

Verify secrets are set:
```bash
supabase secrets list
```

---

## Step 4: Deploy the Function

The function code is already in `supabase/functions/oauth-callback/main.py`

Deploy it:

```bash
supabase functions deploy oauth-callback
```

Expected output:
```
Deployed function oauth-callback
 Function URL: https://your-project.supabase.co/functions/v1/oauth-callback
```

---

## Step 5: Update OAuth Provider Redirect URIs

### In Supabase Dashboard:

1. Go to **Authentication → Providers → Google** (or GitHub)
2. Update **Redirect URLs** to:
   ```
   https://your-project.supabase.co/functions/v1/oauth-callback
   ```

3. In Google Cloud / GitHub OAuth App settings, also update the callback URL to match

---

## Step 6: Test the Edge Function

### Via Browser

```
https://your-project.supabase.co/functions/v1/oauth-callback?code=test_code
```

Should return a 302 redirect to `/login?error=token_exchange_failed`

### Via cURL

```bash
curl -i https://your-project.supabase.co/functions/v1/oauth-callback?code=test
```

---

## Step 7: Update Frontend

Update `login.html` to use Edge Function instead of FastAPI:

**Before:**
```javascript
const { error } = await supabaseClient.auth.signInWithOAuth({
  provider: provider,
  options: {
    redirectTo: window.location.origin + '/api/auth/callback'
  }
});
```

**After:**
```javascript
const { error } = await supabaseClient.auth.signInWithOAuth({
  provider: provider,
  options: {
    redirectTo: 'https://your-project.supabase.co/functions/v1/oauth-callback'
  }
});
```

Or keep it dynamic:

```javascript
const callbackUrl = process.env.EDGE_FUNCTION_ENABLED === 'true'
  ? 'https://your-project.supabase.co/functions/v1/oauth-callback'
  : window.location.origin + '/api/auth/callback';

const { error } = await supabaseClient.auth.signInWithOAuth({
  provider: provider,
  options: { redirectTo: callbackUrl }
});
```

---

## Step 8: Monitor Function Logs

View function execution logs:

```bash
supabase functions logs oauth-callback
```

Or in **Supabase Dashboard → Edge Functions → oauth-callback → Logs**

---

## Function Architecture

```
1. OAuth Provider redirects to Edge Function
   ↓
2. Edge Function extracts ?code parameter
   ↓
3. Edge Function calls Supabase Auth API
   code → tokens (secure server-side exchange)
   ↓
4. Edge Function checks/creates user profile
   ↓
5. Edge Function sets HTTPOnly cookies
   ↓
6. Edge Function redirects to /onboarding or /dashboard
```

---

## Troubleshooting

### Function not deploying

```bash
# Check function syntax
supabase functions validate

# View detailed error
supabase functions deploy oauth-callback --debug
```

### "Missing environment variables" error

```bash
# Verify secrets are set
supabase secrets list

# Re-deploy secrets
supabase secrets set --env-file .env.supabase

# Redeploy function
supabase functions deploy oauth-callback
```

### OAuth still redirecting to old URL

1. Check `login.html` redirectTo URL
2. Check OAuth provider settings (Google/GitHub)
3. Clear browser cache
4. Test in incognito window

### "Invalid authorization code"

1. Check token exchange is reaching Edge Function
2. View logs: `supabase functions logs oauth-callback`
3. Verify Supabase credentials in secrets
4. Confirm OAuth provider is enabled in Supabase

### Cookies not setting

Edge Functions run on Supabase domain, not your app domain:
- Edge Function domain: `your-project.supabase.co`
- App domain: `your-domain.com`

**Solution:** Cookies need `Domain` attribute set:

```python
response_headers = {
  "Set-Cookie": [
    f"sb-access-token={token}; Domain=.your-domain.com; Path=/; HttpOnly; Secure; SameSite=Lax",
  ]
}
```

Or use a [database session store](https://supabase.com/docs/guides/auth/managing-sessions) instead.

---

## Advanced: Running Both FastAPI + Edge Function

You can use both simultaneously:

**FastAPI** handles:
- Email/password auth (`/api/auth/flow`)
- Profile management
- Custom business logic

**Edge Function** handles:
- OAuth callbacks
- Token exchange

Update `login.html`:

```javascript
// Email/password → FastAPI
fetch('/api/auth/flow', { ... })

// OAuth → Edge Function
supabaseClient.auth.signInWithOAuth({
  options: {
    redirectTo: 'https://your-project.supabase.co/functions/v1/oauth-callback'
  }
})
```

---

## Deployment Strategies

### Strategy A: Edge Function Only (Serverless)

```
OAuth → Edge Function → /onboarding
Email/Password → ??? (Need to implement in Edge Function or elsewhere)
```

**Pros:** No server to manage, scales automatically
**Cons:** Must implement all auth logic in Edge Function

### Strategy B: FastAPI + Edge Function (Hybrid)

```
OAuth → Edge Function → /onboarding
Email/Password → FastAPI /api/auth/flow → /onboarding
```

**Pros:** Flexibility, can use both platforms
**Cons:** Multiple services to maintain

### Strategy C: FastAPI Only (Recommended for now)

```
OAuth → FastAPI /api/auth/callback → /onboarding
Email/Password → FastAPI /api/auth/flow → /onboarding
```

**Pros:** Single service, easier to debug
**Cons:** Tied to FastAPI/Vercel

---

## Production Checklist

- [ ] Edge Function deployed
- [ ] Secrets set in Supabase
- [ ] OAuth provider redirect URIs updated
- [ ] Tested OAuth flow end-to-end
- [ ] Cookies setting correctly
- [ ] Error handling working
- [ ] Logs accessible
- [ ] Performance acceptable (<200ms response time)

---

## Performance Optimization

Edge Functions have cold start times (~1-2 seconds first invocation).

Optimize:

1. **Cache imports** - Move imports inside handlers
2. **Use connection pooling** - Reuse HTTP clients
3. **Minimize file size** - Remove unused dependencies
4. **Set timeout appropriately** - 60 seconds default

Current function timeout is 60 seconds (configurable in `deno.json` or `supabase.json`)

---

## Cost Estimation

Supabase Edge Functions pricing (as of 2024):
- **Free tier:** 500K invocations/month included
- **Paid:** $0.000015 per invocation after free tier

For 100,000 OAuth authentications/month:
- **Free tier:** $0
- **Paid (if over 500K):** ~$1.50/month

---

## Next Steps

1. Test Edge Function in staging
2. Monitor logs and performance
3. Set up alerts for errors
4. Plan rollout strategy

---

## Resources

- [Supabase Edge Functions Docs](https://supabase.com/docs/guides/functions)
- [Deploy Python Functions](https://supabase.com/docs/guides/functions/python)
- [Function Configuration](https://supabase.com/docs/guides/functions/manage-functions)
- [Monitoring & Debugging](https://supabase.com/docs/guides/functions/debugging)

---

## Getting Help

1. Check function logs: `supabase functions logs oauth-callback`
2. Review [Supabase docs](https://supabase.com/docs)
3. Check [GitHub discussions](https://github.com/supabase/supabase/discussions)
4. Open [Supabase support ticket](https://supabase.com/docs/support/support-form)
