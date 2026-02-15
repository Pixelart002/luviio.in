# Authentication System - Quick Reference

## 🚀 Setup (5 minutes)

### 1. Environment Variables
```env
SB_URL=https://[project-id].supabase.co
SB_KEY=[anon-key]
SB_SERVICE_ROLE_KEY=[service-role-key]
SESSION_SECRET=<32+ character random string>
```

### 2. Database Table
```sql
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  full_name TEXT,
  avatar_url TEXT,
  bio TEXT,
  onboarded BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile" ON profiles
  FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON profiles
  FOR UPDATE USING (auth.uid() = id);
```

---

## 🔑 API Endpoints

### 1. OAuth Login Initiation
```
GET /api/login?provider=google
```
- Generates PKCE verifier
- Stores in session
- Redirects to OAuth provider

### 2. OAuth Callback Handler
```
GET /api/auth/callback?code=...
```
- Exchanges code for tokens
- Sets secure cookies
- Creates user profile if needed
- Redirects to /dashboard or /onboarding

### 3. Get User Profile
```
GET /api/user/profile
Cookie: sb-access-token=...
```
**Response:**
```json
{
  "success": true,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "provider": "google",
    "created_at": "2024-01-15T10:30:00Z"
  },
  "profile": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "John Doe",
    "bio": "User bio",
    "onboarded": true,
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

### 4. Update User Profile
```
POST /api/user/profile/update
Cookie: sb-access-token=...
Content-Type: application/json

{
  "full_name": "John Doe",
  "bio": "Updated bio",
  "onboarded": true
}
```

### 5. Check Auth Status
```
GET /api/auth/status
```
**Response:**
```json
{
  "authenticated": true,
  "user": {
    "id": "uuid",
    "email": "user@example.com"
  }
}
```

### 6. Logout
```
GET /api/auth/logout
```
- Deletes cookies
- Redirects to /login

---

## 🛡️ Protected Pages

### Dashboard
```
GET /dashboard
Cookie: sb-access-token=...
```
- Checks for valid token
- Redirects to /login if missing
- Shows user profile and statistics

### Client-Side Token Check
```javascript
const response = await fetch("/api/user/profile", {
  credentials: "include"  // Include cookies
});

if (response.status === 401) {
  window.location.href = "/login";  // Redirect if unauthorized
}
```

---

## 🔐 Security Features

| Feature | Status | Details |
|---------|--------|---------|
| PKCE | ✅ | Protects authorization code |
| HttpOnly Cookies | ✅ | Tokens not accessible to JS |
| SameSite=Lax | ✅ | CSRF protection |
| HTTPS Only | ✅ | Secure transport |
| Token Validation | ✅ | Every request verified |
| Session Timeout | ✅ | 10 minutes |
| Profile RLS | ✅ | Users can only access own data |

---

## 🧪 Testing Checklist

```bash
# 1. Login Flow
GET /api/login?provider=google
# → Check: SessionMiddleware sets session cookie
# → Check: Redirect to Google auth URL

# 2. Callback
GET /api/auth/callback?code=AUTH_CODE
# → Check: sb-access-token cookie set
# → Check: Redirect to /dashboard or /onboarding

# 3. Dashboard Access
GET /dashboard
# → Check: Page loads (token valid)
# → Check: User profile displayed

# 4. Protected Endpoint
GET /api/user/profile
# → Check: Returns 200 with user data (token valid)
# → Check: Returns 401 without token

# 5. Logout
GET /api/auth/logout
# → Check: Cookies deleted
# → Check: Redirect to /login

# 6. Invalid Token
# Delete sb-access-token cookie, visit /dashboard
# → Check: Redirect to /login
```

---

## 📋 Code Examples

### Fetch User Profile in Dashboard
```javascript
async function loadUserProfile() {
  try {
    const response = await fetch("/api/user/profile", {
      credentials: "include"
    });

    if (response.status === 401) {
      window.location.href = "/login?redirect=/dashboard";
      return;
    }

    const data = await response.json();
    const user = data.user;
    const profile = data.profile;

    // Update UI
    document.getElementById("user-email").textContent = user.email;
    document.getElementById("profile-name").textContent = 
      profile.full_name || user.email;
  } catch (error) {
    console.error("Error loading profile:", error);
  }
}

document.addEventListener("DOMContentLoaded", loadUserProfile);
```

### Update User Profile
```javascript
async function updateProfile() {
  const response = await fetch("/api/user/profile/update", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      full_name: "John Doe",
      bio: "Updated bio"
    })
  });

  if (response.ok) {
    const data = await response.json();
    console.log("Profile updated:", data.profile);
  } else {
    console.error("Update failed");
  }
}
```

### Logout Handler
```javascript
document.getElementById("logout-btn").addEventListener("click", () => {
  window.location.href = "/api/auth/logout";
});
```

---

## 🐛 Common Issues

| Issue | Solution |
|-------|----------|
| "Takes 3 positional arguments but 4 were given" | ✅ Fixed - Remove REDIRECT_URI from exchange_code call |
| No token after OAuth callback | Check SESSION_SECRET is set, verify callback URL |
| 401 on /api/user/profile | Token expired - need refresh or re-login |
| Dashboard blank after login | Check profile data loads in console |
| Logout doesn't work | Verify /api/auth/logout is called, cookies deleted |
| PKCE verifier missing | Check SessionMiddleware configured, cookies enabled |

---

## 📚 File Structure

```
api/
├── main.py                    # FastAPI app + routes
├── routes/
│   ├── auth.py               # OAuth + auth endpoints
│   └── database.py           # Database utilities
├── utils/
│   └── oauth_client.py       # Supabase OAuth client
└── templates/
    └── app/
        ├── pages/
        │   ├── dashboard.html # Protected dashboard
        │   ├── home.html
        │   └── waitlist.html
        └── auth/
            ├── login.html
            ├── signup.html
            └── onboarding.html
```

---

## 🚀 Deployment Checklist

- [ ] `SESSION_SECRET` set (32+ chars)
- [ ] Supabase credentials configured
- [ ] OAuth redirects configured in provider
- [ ] Database migrations applied
- [ ] HTTPS enforced
- [ ] Cookies tested in production
- [ ] Error handling verified
- [ ] Logs monitored

---

## 📞 Support

For detailed information, see `AUTHENTICATION_PRODUCTION_GUIDE.md`

**Key Topics:**
- OAuth 2.0 with PKCE flow
- Token management & refresh
- Session security
- Database RLS policies
- Attack prevention
- Monitoring & logging
