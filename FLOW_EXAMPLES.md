# OAuth 2.0 Flow Examples

Complete request/response examples for all authentication flows.

---

## 1. OAuth with Google (Happy Path)

### Step 1: User Clicks "Sign with Google"
```javascript
// Frontend: login.html
onclick="oauthLogin('google')"

// Calls Supabase SDK
await client.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: 'https://yourdomain.com/api/auth/callback' }
})

// Supabase redirects user to Google OAuth consent screen
```

### Step 2: User Authorizes
- User sees Google consent screen
- Clicks "Continue"
- Google generates authorization code

### Step 3: Backend Callback
```
GET https://yourdomain.com/api/auth/callback?code=ABC123XYZ&state=...

Backend Processing:
```python
# api/routes/auth.py - oauth_callback()

# 1. Extract code from URL
code = "ABC123XYZ"

# 2. Exchange code for tokens
POST https://enqcujmzxtrbfkaungpm.supabase.co/auth/v1/token?grant_type=authorization_code
{
    "code": "ABC123XYZ",
    "grant_type": "authorization_code"
}

# Response:
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "sbr_xxxxxx",
    "expires_in": 3600,
    "user": {
        "id": "12345678-1234-1234-1234-123456789012",
        "email": "user@gmail.com",
        "email_confirmed_at": "2024-02-13T10:00:00Z"
    }
}
```

### Step 4: Profile Check (3-State Logic)
```python
# Check if profile exists
SELECT * FROM profiles WHERE id = '12345678-1234-1234-1234-123456789012'

# Result: No profile found (New User)
# Action: Create profile with onboarded=False

INSERT INTO profiles (id, email, onboarded)
VALUES (
    '12345678-1234-1234-1234-123456789012',
    'user@gmail.com',
    False
)

# Return path: /onboarding
```

### Step 5: Backend Sets Cookies & Redirects
```python
# Response Headers:
Set-Cookie: sb-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...; 
            HttpOnly; Secure; SameSite=Lax; Max-Age=3600

Set-Cookie: sb-refresh-token=sbr_xxxxxx; 
            HttpOnly; Secure; SameSite=Lax; Max-Age=2592000

Location: /onboarding

# Status: 302 Found (Redirect)
```

### Step 6: User Sees Onboarding
```
Browser follows redirect:
GET /onboarding

Response:
200 OK
<html>
  <!-- Onboarding form -->
</html>
```

---

## 2. Email/Password Signup

### Request
```javascript
// Frontend: signup.html
POST /api/auth/flow
Content-Type: application/json
Credentials: include

{
    "email": "newuser@example.com",
    "password": "SecurePass123",
    "action": "signup"
}
```

### Backend Processing
```python
# api/routes/auth.py - auth_flow_manual()

# 1. Validate input
email = "newuser@example.com"  # ✓ Valid email
password = "SecurePass123"     # ✓ 6+ characters

# 2. Create Supabase auth user
POST https://your-project.supabase.co/auth/v1/signup
Headers: apikey: <SB_KEY>
{
    "email": "newuser@example.com",
    "password": "SecurePass123"
}

# Response:
{
    "id": "87654321-4321-4321-4321-210987654321",
    "email": "newuser@example.com",
    "email_confirmed_at": None,  # Email not confirmed yet
    "user_metadata": {},
    "aud": "authenticated",
    "created_at": "2024-02-13T10:30:00Z"
}

# 3. Create profile
INSERT INTO profiles (id, email, onboarded, created_at)
VALUES (
    '87654321-4321-4321-4321-210987654321',
    'newuser@example.com',
    False,
    NOW()
)

# 4. Send confirmation email via Supabase
# (Automatically handled by Supabase)
```

### Response
```json
{
    "next": "onboarding",
    "msg": "Signup successful! Check email for confirmation."
}

# HTTP Status: 200 OK
```

### Frontend Handling
```javascript
// Frontend shows success message
showSuccess("Signup successful! Check email for confirmation.")

// Redirects after 2 seconds
setTimeout(() => {
    window.location.href = '/login'
}, 2000)
```

---

## 3. Email/Password Login

### Request
```javascript
// Frontend: login.html
POST /api/auth/flow
Content-Type: application/json
Credentials: include

{
    "email": "user@example.com",
    "password": "SecurePass123",
    "action": "login"
}
```

### Backend Processing - User Not Yet Onboarded

```python
# 1. Authenticate with Supabase
POST https://your-project.supabase.co/auth/v1/token?grant_type=password
Headers: apikey: <SB_KEY>
{
    "email": "user@example.com",
    "password": "SecurePass123"
}

# Response:
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "sbr_xxxxxx",
    "expires_in": 3600,
    "token_type": "bearer",
    "user": {
        "id": "12345678-1234-1234-1234-123456789012",
        "email": "user@example.com",
        "email_confirmed_at": "2024-01-15T09:00:00Z"
    }
}

# 2. Check profile status (3-State Logic - STATE B)
SELECT onboarded FROM profiles 
WHERE id = '12345678-1234-1234-1234-123456789012'

# Result: onboarded = False
# Status: STATE B (Incomplete)

# 3. Determine next route: /onboarding
```

### Response
```json
{
    "next": "onboarding",
    "session": {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "refresh_token": "sbr_xxxxxx",
        "expires_in": 3600,
        "user": {
            "id": "12345678-1234-1234-1234-123456789012",
            "email": "user@example.com"
        }
    }
}

# HTTP Status: 200 OK
```

### Backend Processing - User Already Onboarded

```python
# Same auth flow as above, but:

# Check profile status (3-State Logic - STATE C)
SELECT onboarded FROM profiles 
WHERE id = '12345678-1234-1234-1234-123456789012'

# Result: onboarded = True
# Status: STATE C (Complete)

# Determine next route: /dashboard
```

### Response
```json
{
    "next": "dashboard",
    "session": {
        "access_token": "...",
        "refresh_token": "..."
    }
}
```

### Frontend Handling
```javascript
if (data.next === 'onboarding') {
    // Redirect to profile setup
    window.location.href = '/onboarding'
} else if (data.next === 'dashboard') {
    // Redirect to main app
    window.location.href = '/dashboard'
}
```

---

## 4. Invalid Login Attempt

### Request
```javascript
POST /api/auth/flow
{
    "email": "user@example.com",
    "password": "WrongPassword123",
    "action": "login"
}
```

### Backend Processing
```python
# Authenticate with Supabase
POST https://your-project.supabase.co/auth/v1/token?grant_type=password
{
    "email": "user@example.com",
    "password": "WrongPassword123"
}

# Response (Error):
{
    "error": "invalid_credentials",
    "error_description": "Invalid login credentials"
}

# HTTP Status: 401 Unauthorized
```

### Backend Response to Frontend
```json
{
    "error": "Invalid login credentials"
}

# HTTP Status: 401 Unauthorized
```

### Frontend Handling
```javascript
if (!res.ok) {
    const data = await res.json()
    showError(data.error)  // Shows: "Invalid login credentials"
}
```

---

## 5. Validation Error - Email Already Exists

### Request
```javascript
POST /api/auth/flow
{
    "email": "existing@example.com",
    "password": "NewPass123",
    "action": "signup"
}
```

### Backend Processing
```python
# Create auth user
POST https://your-project.supabase.co/auth/v1/signup
{
    "email": "existing@example.com",
    "password": "NewPass123"
}

# Response (Error):
{
    "error": "user_already_exists",
    "error_description": "A user with this email address has already been registered"
}
```

### Backend Response
```json
{
    "error": "A user with this email address has already been registered"
}

# HTTP Status: 400 Bad Request
```

---

## 6. Logout

### Request
```javascript
// Frontend: logout button
window.location.href = '/api/auth/logout'
```

### Backend Processing
```python
# api/routes/auth.py - logout()

# Response Headers:
Set-Cookie: sb-access-token=; 
            HttpOnly; Secure; SameSite=Lax; Max-Age=0

Set-Cookie: sb-refresh-token=; 
            HttpOnly; Secure; SameSite=Lax; Max-Age=0

Location: /login

# Status: 302 Found (Redirect)
```

### User Experience
```
1. User clicks "Logout" button
2. Cookies cleared
3. User redirected to /login
4. User sees login page
```

---

## 7. Session Status Check (Optional)

### Request
```javascript
// Frontend: dashboard.html
GET /api/auth/status

// Automatically sends cookies:
// Cookie: sb-access-token=eyJ...
```

### Backend Processing
```python
# Extract token from cookies
access_token = request.cookies.get("sb-access-token")

# Verify token with Supabase
GET https://your-project.supabase.co/auth/v1/user
Headers: 
    Authorization: Bearer eyJ...
    apikey: <SB_KEY>

# Response:
{
    "id": "12345678-1234-1234-1234-123456789012",
    "email": "user@example.com",
    "email_confirmed_at": "2024-02-13T10:00:00Z",
    "phone": None,
    "confirmed_at": "2024-02-13T10:00:00Z",
    "last_sign_in_at": "2024-02-13T10:15:00Z",
    "app_metadata": {},
    "user_metadata": {}
}
```

### Backend Response
```json
{
    "authenticated": true,
    "user": {
        "id": "12345678-1234-1234-1234-123456789012",
        "email": "user@example.com"
    }
}

# HTTP Status: 200 OK
```

### If Not Authenticated
```json
{
    "authenticated": false
}

# HTTP Status: 401 Unauthorized
```

---

## 8. OAuth Callback Error - Expired Code

### Request
```
GET https://yourdomain.com/api/auth/callback?code=EXPIRED_CODE&state=...
```

### Backend Processing
```python
# Exchange code (expired)
POST https://your-project.supabase.co/auth/v1/token?grant_type=authorization_code
{
    "code": "EXPIRED_CODE",
    "grant_type": "authorization_code"
}

# Response (Error):
{
    "error": "invalid_code",
    "error_description": "Authorization code has expired"
}
```

### Backend Response
```
Location: /login?error=invalid_code&msg=Authorization+code+has+expired

# Status: 302 Found (Redirect)
```

### Frontend Handling
```javascript
// URL params show error
window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search)
    const error = params.get('error')
    const msg = params.get('msg')
    
    if (error) {
        showError(msg || `Error: ${error}`)
    }
})

// User sees: "Authorization code has expired"
```

---

## 9. Complete User Journey (Success)

### Timeline
```
10:00:00 - User visits https://yourdomain.com/signup
10:00:05 - User clicks "Sign with Google"
10:00:10 - Google consent screen shown
10:00:30 - User clicks "Continue"
10:00:35 - Browser redirects to /api/auth/callback?code=ABC123
10:00:36 - Backend exchanges code for tokens
10:00:37 - Backend creates profile (onboarded=False)
10:00:38 - Backend sets cookies
10:00:39 - Backend redirects to /onboarding
10:00:40 - User sees onboarding form
10:01:00 - User completes onboarding
10:01:05 - Backend updates profile (onboarded=True)
10:01:10 - User redirected to /dashboard
10:01:15 - User sees dashboard
```

### Database State
```
BEFORE:
profiles table: EMPTY

AFTER Google OAuth + Onboarding:
profiles table:
┌──────────────────────────────────┬─────────────────┬───────────┐
│ id                               │ email           │ onboarded │
├──────────────────────────────────┼─────────────────┼───────────┤
│ 12345678-1234-1234-1234-123...   │ user@gmail.com  │ true      │
└──────────────────────────────────┴─────────────────┴───────────┘
```

---

## 10. Error Handling Summary

### Common HTTP Status Codes

| Status | Scenario | Response |
|--------|----------|----------|
| 200 | Success | `{"next": "onboarding", "session": {...}}` |
| 302 | Redirect (OAuth) | `Location: /onboarding` |
| 400 | Bad request | `{"error": "Email already exists"}` |
| 401 | Unauthorized | `{"error": "Invalid credentials"}` |
| 403 | Forbidden | `{"error": "Access denied"}` |
| 500 | Server error | `{"error": "Server error - try again"}` |
| 503 | Service unavailable | `{"error": "Server timeout"}` |

### Error Messages

```javascript
// User sees these on frontend:
"Invalid credentials"
"Email already exists"
"Password must be at least 6 characters"
"Please fill in all fields"
"Server error - try again later"
"Authorization failed"
"OAuth failed"
```

---

## API Quick Reference

### Authentication Endpoints

```bash
# OAuth Callback
GET /api/auth/callback?code=...

# Manual Auth
POST /api/auth/flow
Content-Type: application/json
{
    "email": "user@example.com",
    "password": "password",
    "action": "login|signup"
}

# Logout
GET /api/auth/logout

# Status Check (Optional)
GET /api/auth/status
```

---

This document provides complete examples of all authentication flows with request/response cycles, status codes, and error scenarios.
