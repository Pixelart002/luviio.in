# ✅ OAuth 2.0 Implementation Checklist

## Phase 1: Setup (2-3 hours)

### Environment Configuration
- [ ] Add `SB_URL` to environment variables
- [ ] Add `SB_KEY` (anon key) to environment variables  
- [ ] Add `SB_SERVICE_ROLE_KEY` to environment variables
- [ ] Restart development server
- [ ] Verify no "Missing environment variables" warnings

### Database Setup
- [ ] Go to Supabase Dashboard
- [ ] Open SQL Editor
- [ ] Copy and paste profiles table SQL
- [ ] Execute SQL
- [ ] Verify `profiles` table exists
- [ ] Enable Row Level Security (RLS)
- [ ] Create "read own profile" policy
- [ ] Create "update own profile" policy
- [ ] Test policies with test user

### OAuth Provider Configuration

#### Google OAuth
- [ ] Go to Google Cloud Console
- [ ] Create new project or select existing
- [ ] Enable Google+ API
- [ ] Create OAuth 2.0 credentials (Web Application)
- [ ] Add Authorized Redirect URI: `http://localhost:8000/api/auth/callback`
- [ ] Add Authorized Redirect URI: `https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback`
- [ ] Add Authorized Redirect URI: `https://your-domain.com/api/auth/callback` (production)
- [ ] Copy Client ID
- [ ] Copy Client Secret
- [ ] Go to Supabase Dashboard
- [ ] Navigate to Authentication → Providers → Google
- [ ] Enable Google
- [ ] Paste Client ID
- [ ] Paste Client Secret
- [ ] Click Save
- [ ] Verify Google provider is enabled

#### GitHub OAuth
- [ ] Go to GitHub Settings → Developer Settings → OAuth Apps
- [ ] Click "Create New OAuth App"
- [ ] Set Application Name
- [ ] Set Homepage URL: `https://enqcujmzxtrbfkaungpm.supabase.co` (or your domain)
- [ ] Set Authorization callback URL: `https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback`
- [ ] Also add: `https://your-domain.com/api/auth/callback` (for production)
- [ ] Create Application
- [ ] Copy Client ID
- [ ] Generate and copy Client Secret
- [ ] Go to Supabase Dashboard
- [ ] Navigate to Authentication → Providers → GitHub
- [ ] Enable GitHub
- [ ] Paste Client ID
- [ ] Paste Client Secret
- [ ] Click Save
- [ ] Verify GitHub provider is enabled

---

## Phase 2: Local Testing (1-2 hours)

### Code Verification
- [ ] Review `api/utils/oauth_client.py` exists (423 lines)
- [ ] Review `api/routes/auth.py` has OAuth handler
- [ ] Review `api/templates/app/auth/login.html` has OAuth buttons
- [ ] Review `api/templates/app/auth/signup.html` exists
- [ ] Review `api/templates/macros/auth_macros.html` has form components

### Start Development Server
- [ ] Navigate to api directory: `cd api`
- [ ] Start uvicorn: `uvicorn main:app --reload`
- [ ] Verify no errors in console
- [ ] Verify server running on `http://localhost:8000`

### OAuth Flow Testing

#### Google OAuth
- [ ] Open browser: `http://localhost:8000/login`
- [ ] Click "Google" button
- [ ] Redirected to Google login
- [ ] Sign in with Google account
- [ ] See "Sign in with Google" success
- [ ] Redirected back to app
- [ ] Check URL (should not have `#access_token`)
- [ ] Check if redirected to `/onboarding` (first time)
- [ ] Open DevTools → Application → Cookies
- [ ] Verify `sb-access-token` cookie exists
- [ ] Verify `sb-access-token` is HttpOnly (no JS access)
- [ ] Verify `sb-access-token` has Secure flag (HTTPS only)
- [ ] Verify `sb-access-token` has SameSite=Lax
- [ ] Verify `sb-refresh-token` cookie exists
- [ ] Check page content loads
- [ ] Logout works (`/api/auth/logout`)

#### GitHub OAuth
- [ ] Go to `/login` page
- [ ] Click "GitHub" button
- [ ] Redirected to GitHub login
- [ ] Sign in with GitHub
- [ ] Authorize application
- [ ] Redirected back to app
- [ ] Redirected to `/onboarding` (first time)
- [ ] Verify cookies set correctly
- [ ] Same checks as Google above

### Email/Password Flow Testing

#### Signup
- [ ] Go to `/login` page
- [ ] Click "Create one" to switch to signup
- [ ] Enter valid email: `test@example.com`
- [ ] Enter password: `testpassword123`
- [ ] Check terms checkbox
- [ ] Click "Create Account"
- [ ] See success message
- [ ] Wait 2 seconds (redirect)
- [ ] Should redirect to `/login`
- [ ] Check inbox for confirmation email (if email service enabled)

#### Login with New Account
- [ ] Go to `/login` page
- [ ] Enter email: `test@example.com`
- [ ] Enter password: `testpassword123`
- [ ] Click "Sign In"
- [ ] See success message
- [ ] Redirected to `/onboarding` (if profile.onboarded=false)
- [ ] Check cookies set

#### Error Cases
- [ ] Try signup with invalid email → Error shown
- [ ] Try signup with short password → Error shown
- [ ] Try login with wrong password → Error shown
- [ ] Try login with non-existent email → Error shown

### Session Management Testing
- [ ] Open DevTools Console
- [ ] Test auth status: 
  ```javascript
  fetch('/api/auth/status', { credentials: 'include' })
    .then(r => r.json())
    .then(console.log)
  ```
- [ ] Should see: `{ authenticated: true, user: {...} }`
- [ ] Logout: `/api/auth/logout`
- [ ] Test auth status again
- [ ] Should see: `{ authenticated: false }`

---

## Phase 3: Pre-Production (1 hour)

### Code Review
- [ ] Review `api/utils/oauth_client.py` for security
- [ ] Review `api/routes/auth.py` error handling
- [ ] Check all environment variables are used correctly
- [ ] Verify no credentials in code
- [ ] Verify no debug logging in production
- [ ] Check timeout values are reasonable

### Documentation Review
- [ ] Read `docs/README.md`
- [ ] Read `docs/OAUTH_QUICK_REFERENCE.md`
- [ ] Read `docs/OAUTH_SETUP.md` security section
- [ ] Understand 3-State Logic
- [ ] Understand OAuth flow
- [ ] Know how to debug issues

### Security Audit
- [ ] ✅ OAuth 2.0 Authorization Code Flow (not implicit)
- [ ] ✅ PKCE support enabled
- [ ] ✅ Server-side token exchange (code exchanged for tokens)
- [ ] ✅ Tokens never in URL or local storage
- [ ] ✅ HTTPOnly cookies used for storage
- [ ] ✅ Secure flag set (HTTPS required)
- [ ] ✅ SameSite=Lax for CSRF protection
- [ ] ✅ Token expiration set (1 hour)
- [ ] ✅ Refresh token expiration set (30 days)
- [ ] ✅ Input validation in place
- [ ] ✅ Error messages don't leak info
- [ ] ✅ Rate limiting configured
- [ ] ✅ CORS configured correctly
- [ ] ✅ No credentials in logs

### Configuration Review
- [ ] Environment variables complete
- [ ] Profiles table created correctly
- [ ] RLS policies enabled
- [ ] OAuth providers enabled and configured
- [ ] Redirect URLs configured correctly
- [ ] All required dependencies installed

---

## Phase 4: Production Deployment (1-2 hours)

### Pre-Deployment Checklist
- [ ] All tests passed locally
- [ ] No console errors or warnings
- [ ] No hardcoded credentials
- [ ] Environment variables ready for production
- [ ] Backup of code
- [ ] Backup of database

### Vercel Deployment
- [ ] Push code to GitHub: `git push origin main`
- [ ] Verify GitHub branch is up to date
- [ ] Go to Vercel Dashboard
- [ ] Check build log (should succeed)
- [ ] Verify environment variables are set
  - [ ] SB_URL
  - [ ] SB_KEY
  - [ ] SB_SERVICE_ROLE_KEY
- [ ] Check deployment is live
- [ ] Test OAuth with production domain

### Update OAuth Provider URLs
- [ ] Go to Google Cloud Console
- [ ] Update authorized redirect URI to production URL
  - [ ] `https://your-domain.com/api/auth/callback`
- [ ] Go to GitHub OAuth App
- [ ] Update Authorization callback URL to production URL
  - [ ] `https://your-domain.com/api/auth/callback`
- [ ] Go to Supabase Dashboard
- [ ] Verify OAuth providers still enabled
- [ ] Verify credentials still correct

### Post-Deployment Testing

#### OAuth Flow
- [ ] Test Google OAuth with production domain
- [ ] Test GitHub OAuth with production domain
- [ ] Verify redirects work
- [ ] Verify cookies set with correct domain
- [ ] Verify Secure flag (HTTPS only)

#### Email/Password Flow
- [ ] Test signup on production
- [ ] Test login on production
- [ ] Verify email confirmation works
- [ ] Test password reset (if implemented)

#### Session Management
- [ ] Test `/api/auth/status` returns correct data
- [ ] Test logout works
- [ ] Test cookies cleared after logout
- [ ] Test token refresh (if implemented)

### Monitoring Setup
- [ ] Enable Vercel Analytics
- [ ] Set up error monitoring (Sentry, etc.)
- [ ] Set up uptime monitoring
- [ ] Check Supabase Logs
- [ ] Configure alerts for errors

---

## Phase 5: Post-Launch (Ongoing)

### Weekly Checks
- [ ] [ ] Review logs for errors
- [ ] [ ] Check authentication success rate
- [ ] [ ] Monitor failed login attempts
- [ ] [ ] Review performance metrics
- [ ] [ ] Check for security alerts

### Monthly Checks
- [ ] Review token expiration patterns
- [ ] Check for unused OAuth sessions
- [ ] Update dependencies if needed
- [ ] Review database queries for optimization
- [ ] Check for slow endpoints

### Security Reviews
- [ ] Keep dependencies updated
- [ ] Review security advisories
- [ ] Test error handling edge cases
- [ ] Audit logs for suspicious activity
- [ ] Review and update security policies

---

## Feature Completion Checklist

### Core OAuth
- [x] Google OAuth
- [x] GitHub OAuth
- [x] Authorization Code Flow (PKCE)
- [x] Server-side token exchange
- [x] HTTPOnly cookies

### Email/Password
- [x] Signup functionality
- [x] Login functionality
- [x] Password validation
- [x] Email validation
- [x] Account creation

### User Management
- [x] Profile creation
- [x] Profile verification
- [x] Onboarding flag
- [x] User status check
- [x] Session management

### Security
- [x] HTTPS/Secure flag
- [x] SameSite CSRF protection
- [x] Token expiration
- [x] Input validation
- [x] Error handling
- [x] Rate limiting ready
- [x] RLS policies
- [x] No credential leaks

### Developer Experience
- [x] OAuth client library
- [x] Comprehensive documentation
- [x] Quick start guide
- [x] API documentation
- [x] Error handling
- [x] Logging
- [x] Testing guides
- [x] Deployment guides

---

## Documentation Checklist

- [x] Quick Reference Guide
- [x] Quick Start Guide
- [x] Complete Setup Guide
- [x] Edge Function Guide
- [x] Implementation Summary
- [x] This Checklist
- [x] Code comments
- [x] Error messages

---

## Ready for Production?

Check these boxes before going live:

- [ ] All Phase 1-4 checklists completed
- [ ] Local testing passed
- [ ] Production testing passed
- [ ] Security audit passed
- [ ] Monitoring configured
- [ ] Error handling tested
- [ ] Documentation reviewed
- [ ] Team trained on system
- [ ] Backup plan in place
- [ ] Rollback plan in place

**If all boxes are checked, you're ready for production! 🚀**

---

## Troubleshooting Reference

| Issue | Checklist Item | Solution |
|-------|---|----------|
| OAuth not working | Google/GitHub config | Verify credentials and redirect URLs |
| Cookies not setting | HTTPS/Domain config | Check browser DevTools, verify HTTPS |
| Profile not created | Database setup | Check profiles table, RLS policies |
| Token expired | Token config | Implement refresh logic |
| Login fails | Email/Password config | Check credentials, verify user exists |

---

## Keep This Checklist Handy

Print or bookmark this checklist for:
- New feature additions
- Troubleshooting
- Production deployments
- Team onboarding
- Security audits

---

**Last Updated:** 2024
**Version:** 1.0.0
**Status:** Ready for Use ✅
