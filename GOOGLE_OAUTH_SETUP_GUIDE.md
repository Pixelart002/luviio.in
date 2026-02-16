# 🛠️ Google OAuth Setup Guide for Luviio

If you are seeing a **"redirect_uri_mismatch"** or a UI mismatch on the Google OAuth screen, it means the URL configured in your Google Cloud Console does not exactly match the one being sent by the application.

Follow these steps to fix it.

---

## 1. Identify Your Exact Redirect URI

The enterprise auth system uses the following logic for the Redirect URI:
- **Base URL:** `https://luviio.in` (from the `BASE_URL` environment variable)
- **Callback Path:** `/api/auth/callback`
- **Full Redirect URI:** `https://luviio.in/api/auth/callback`

> [!IMPORTANT]
> Google is extremely strict. `https://luviio.in` is NOT the same as `https://www.luviio.in`. Ensure you use the one without `www` if that is how your `BASE_URL` is set.

---

## 2. Update Google Cloud Console

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Navigate to **APIs & Services** > **Credentials**.
3.  Find your OAuth 2.0 Client ID under the **OAuth 2.0 Client IDs** section and click the edit icon (pencil).
4.  Scroll down to **Authorized redirect URIs**.
5.  Add the following URI:
    ```text
    https://luviio.in/api/auth/callback
    ```
6.  (Optional) If you test locally, also add:
    ```text
    http://localhost:8000/api/auth/callback
    ```
7.  Click **Save**.

---

## 3. Update Supabase Dashboard

Supabase acts as the middleman. It also needs to know about this URI.

1.  Go to your [Supabase Dashboard](https://supabase.com/dashboard).
2.  Navigate to **Authentication** > **URL Configuration**.
3.  In the **Redirect URIs** section, add:
    ```text
    https://luviio.in/api/auth/callback
    ```
4.  Ensure your **Site URL** is set to:
    ```text
    https://luviio.in
    ```
5.  Click **Save**.

---

## 4. Verify Vercel Environment Variables

Ensure your Vercel project has the following environment variables set correctly:

| Variable | Value |
| :--- | :--- |
| `BASE_URL` | `https://luviio.in` |
| `SB_URL` | `https://enqcujmzxtrbfkaungpm.supabase.co` |

> [!TIP]
> After changing environment variables in Vercel, you **must** redeploy the project for the changes to take effect.

---

## 5. Troubleshooting "UI Mismatch"

If the screen looks "old" or says "The app hasn't been verified," this is usually due to the **OAuth Consent Screen** settings:

1.  In Google Cloud Console, go to **APIs & Services** > **OAuth consent screen**.
2.  Ensure the **App name**, **User support email**, and **Developer contact info** are filled out.
3.  If your app is in "Testing" mode, only the users you add under "Test users" can log in. Move it to "Production" mode if you want anyone to use it (this may require a basic verification process if you use sensitive scopes).

---

## ✅ Summary Checklist
- [ ] Google Console Redirect URI: `https://luviio.in/api/auth/callback`
- [ ] Supabase Redirect URI: `https://luviio.in/api/auth/callback`
- [ ] Vercel `BASE_URL`: `https://luviio.in`
- [ ] All URLs use `https` (except localhost) and NO `www`.
