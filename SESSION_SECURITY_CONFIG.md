# Session Security & Configuration Guide

## 🔐 Current Configuration

```python
# api/main.py
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.environ.get("SESSION_SECRET", "fallback-key"),
    session_cookie="luviio_session",
    same_site="lax",     # Allows OAuth redirects from external origins
    https_only=True,     # Only sent over HTTPS (production)
    max_age=600          # Expires after 10 minutes
)
```

---

## 📋 Configuration Explanation

### `secret_key` (Critical)
- **Purpose**: Encrypts session data before storing in cookies
- **Requirement**: Must be 32+ character cryptographically random string
- **Security Level**: HIGH - If compromised, session data can be decrypted

**Generate secure key:**
```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Output example:
# rBf1_8K2z-L5hJ9qQ3xW7vP2nM4rT6yU8sA

# Then add to Vercel environment variables as SESSION_SECRET
```

### `session_cookie`
- **Name**: `luviio_session`
- **Contains**: Session ID (encrypted by FastAPI)
- **NOT Contains**: Tokens (tokens go in separate cookies)

### `same_site`
- **Setting**: `"lax"` (current, correct for OAuth)
- **Alternatives**:
  - `"strict"`: Most secure but breaks OAuth redirects
  - `"lax"`: Good balance (allows safe cross-site requests)
  - `"none"`: Requires Secure=True (vulnerable)

**OAuth Requirement:**
OAuth providers redirect user back to your app → requires `same_site="lax"`

### `https_only`
- **Setting**: `True` (production)
- **Effect**: Cookies only sent over HTTPS
- **Important**: Vercel enforces HTTPS, so this is safe

**Local Development:**
```python
import os
https_only = not os.environ.get("DEBUG")  # False in dev
```

### `max_age`
- **Setting**: `600` seconds (10 minutes)
- **Why**: Enough time for OAuth code exchange
- **Security**: Shorter = less time for session fixation attacks

**Timeline:**
1. User initiates login (0:00)
2. PKCE verifier stored in session
3. User redirected to OAuth provider
4. User logs in with OAuth provider
5. OAuth provider redirects back (typically within 2 minutes)
6. Session used to retrieve verifier
7. Session cleaned up after OAuth exchange

---

## 🛡️ Token Storage Strategy

### Session Cookie (Created by SessionMiddleware)
```
Name: luviio_session
Value: [encrypted-session-id]
Flags: HttpOnly, Secure, SameSite=Lax
Max-Age: 600 (10 minutes)
Purpose: Store PKCE verifier during OAuth flow
```

### Access Token Cookie (Set by OAuth callback)
```
Name: sb-access-token
Value: [JWT-token]
Flags: HttpOnly, Secure, SameSite=Lax
Max-Age: 3600 (1 hour)
Purpose: Authenticate API requests & page access
```

### Refresh Token Cookie (Set by OAuth callback)
```
Name: sb-refresh-token
Value: [JWT-token]
Flags: HttpOnly, Secure, SameSite=Lax
Max-Age: 2592000 (30 days)
Purpose: Get new access token when expired
```

**Three separate cookies = Defense in depth:**
- Session expires → New PKCE flow required
- Access token expires → Automatic refresh
- Refresh token expires → Full re-login required

---

## 🔄 Session Lifecycle

```
Timeline: OAuth Flow

T=0:00   [User clicks "Login with Google"]
         GET /api/login?provider=google
         
         Server:
         - Generates PKCE verifier (64 bytes random)
         - Stores: request.session["code_verifier"] = verifier
         - Creates SessionMiddleware cookie (encrypted)
         - Redirects to Google

T=0:05   [User approves Google consent]
         Google redirects to /api/auth/callback?code=...
         
         Browser sends requests with:
         - Cookie: luviio_session=[encrypted-verifier]
         - Query param: code=AUTHORIZATION_CODE

T=0:06   [Callback handler]
         Server:
         - Retrieves code_verifier from session
         - Exchanges code + verifier for tokens
         - request.session.pop("code_verifier")  ← Cleanup
         - Sets sb-access-token & sb-refresh-token cookies
         - Deletes luviio_session after exchange

T=0:10   [User on dashboard]
         Every request includes:
         - Cookie: sb-access-token (active)
         - Cookie: sb-refresh-token (inactive unless expired)
         
         Server validates access_token on:
         - GET /dashboard
         - GET /api/user/profile
         - POST /api/user/profile/update

T=1:00   [Access token expired]
         Browser requests new token via refresh
         Server issues new access token (same refresh token)

T=30:00  [Refresh token expired]
         User must login again (new PKCE flow)
         GET /api/login?provider=google
```

---

## 🚨 Session Security Best Practices

### 1. Secure Secret Generation
```python
# ✅ CORRECT - Cryptographically secure
import secrets
session_secret = secrets.token_urlsafe(32)  # 32+ bytes

# ❌ WRONG - Not random enough
session_secret = "my_password_123"
session_secret = "abcdefghijklmnopqrstuvwxyz123456"
```

### 2. Never Store Sensitive Data in Session
```python
# ✅ SAFE - Store only verifier (temporary)
request.session["code_verifier"] = verifier

# ❌ DANGEROUS - Never store tokens in session
request.session["access_token"] = access_token  # Use cookies instead
request.session["user_password"] = password    # Never store passwords
```

### 3. Clean Up After Use
```python
# ✅ CORRECT - Remove verifier after exchange
request.session.pop("code_verifier", None)

# ❌ WRONG - Leaving data in session
# code_verifier stays until session timeout
```

### 4. Handle Session Timeout
```python
@router.get("/api/auth/callback")
async def oauth_callback(request: Request, code: str = None):
    code_verifier = request.session.get("code_verifier")
    
    if not code_verifier:
        # Session expired (> 10 minutes)
        return RedirectResponse("/login?error=session_expired")
    
    # Proceed with token exchange
```

### 5. Monitor Session Errors
```python
import logging
logger = logging.getLogger("AUTH")

try:
    code_verifier = request.session.get("code_verifier")
    if not code_verifier:
        logger.warning("Session expired during OAuth callback")
except Exception as e:
    logger.error(f"Session error: {str(e)}")
```

---

## 🧪 Testing Session Configuration

### Test 1: Verify Session Cookie Set
```bash
# 1. Start server
python -m uvicorn api.main:app --reload

# 2. Visit login
curl -i http://localhost:8000/api/login?provider=google

# 3. Check response headers
# Should see:
# set-cookie: luviio_session=...; Path=/; HttpOnly; SameSite=lax
```

### Test 2: Verify PKCE Verifier Storage
```bash
# In dev, add debug logging to auth.py
import logging
logger = logging.getLogger()

@router.get("/login")
async def login_init(request: Request, provider: str = "google"):
    code_verifier = secrets.token_urlsafe(64)
    request.session["code_verifier"] = code_verifier
    
    logger.info(f"[DEBUG] Verifier stored: {code_verifier[:10]}...")  # Log first 10 chars
    # ...
```

### Test 3: Verify Session Cleanup
```bash
# Check that code_verifier is removed after callback
@router.get("/auth/callback")
async def oauth_callback(request: Request, code: str = None):
    code_verifier = request.session.pop("code_verifier", None)
    logger.info(f"[DEBUG] Verifier removed: {code_verifier is None}")  # Should be True
```

### Test 4: Session Timeout
```bash
# 1. Start login (creates session)
GET /api/login?provider=google

# 2. Wait 11 minutes
# 3. Complete OAuth callback
GET /api/auth/callback?code=...

# Should see: "Session expired" error
# Because max_age=600 (10 minutes) expired
```

---

## 🔧 Production Adjustments

### Option 1: Keep Session Short (Current)
```python
max_age=600  # 10 minutes
# Pros: Very secure, impossible to intercept OAuth flow
# Cons: If OAuth takes >10 minutes, user must retry
```

### Option 2: Longer Session for Slow Connections
```python
max_age=1800  # 30 minutes
# Pros: Better for slow networks or OAuth delays
# Cons: Longer window for session fixation attacks
```

### Option 3: Strict SameSite (Extra Security)
```python
same_site="strict"
# Pros: Strongest CSRF protection
# Cons: OAuth redirects may fail in some browsers
# Recommendation: Test before deploying
```

---

## 📊 Session vs Token Comparison

| Aspect | Session | Access Token | Refresh Token |
|--------|---------|-------------|---------------|
| Purpose | OAuth flow | API authentication | Token renewal |
| Lifetime | 10 min | 1 hour | 30 days |
| Storage | Session cookie | HttpOnly cookie | HttpOnly cookie |
| Contains | PKCE verifier | JWT (user ID, etc) | Encrypted refresh token |
| Sent with | Requests to same domain | All API requests | Token refresh only |
| Cleanup | Auto-expire + manual | Auto-expire | Manual logout |

---

## 🚀 Environment Variable Checklist

```bash
# Required for SESSION_SECURITY_CONFIG
SESSION_SECRET=<32+ char random string>   # ✅ CRITICAL

# Required for OAuth
SB_URL=https://[id].supabase.co           # ✅ Set
SB_KEY=[anon-key]                         # ✅ Set
SB_SERVICE_ROLE_KEY=[service-role]        # ✅ Set

# Verification
echo $SESSION_SECRET    # Should be 32+ chars
echo $SB_URL           # Should be valid URL
echo $SB_KEY           # Should be non-empty
```

**Vercel Setup:**
```bash
# In Vercel Dashboard
Settings → Environment Variables → Add
KEY: SESSION_SECRET
VALUE: <generate from `secrets.token_urlsafe(32)` or similar>
```

---

## 🔍 Debugging Sessions

### View All Cookies (Browser DevTools)
```javascript
// In browser console
document.cookie
// Output: "luviio_session=...; sb-access-token=..."
```

### Check Session Data (Server-Side)
```python
@router.get("/debug/session")
async def debug_session(request: Request):
    # Only enable in development!
    if not os.environ.get("DEBUG"):
        return {"error": "Not in debug mode"}
    
    return {
        "session_data": dict(request.session),
        "cookies": dict(request.cookies)
    }
```

### Monitor Session Middleware
```python
import logging
logging.getLogger("starlette.middleware.sessions").setLevel(logging.DEBUG)
```

---

## Summary

✅ **Current Configuration is Secure:**
- Session secret encrypted (if SESSION_SECRET is set)
- PKCE verifier stored safely in session
- Session timeout (10 min) prevents interception
- Tokens in separate HttpOnly cookies
- SameSite=Lax allows OAuth while preventing CSRF

⚠️ **Critical Step:**
- Set `SESSION_SECRET` environment variable (32+ chars)
- Without it, session data is encrypted with fallback key (insecure)

🚀 **Result:**
- Production-ready OAuth 2.0 with PKCE
- Session-based PKCE verifier storage
- Secure token exchange and storage
- Complete protection against common attacks
