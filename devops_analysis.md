# DevOps Analysis and Proposed Fixes for Luviio Monorepo

This document outlines the current DevOps structure of the `Pixelart002/luviio.in` monorepo, identifies areas for improvement, and proposes solutions to correctly configure the Vercel deployment and connect the frontend to the backend API.

## 1. Current Repository Structure Overview

The repository is structured as a monorepo containing two main applications:

-   **`backend/`**: A FastAPI application serving as the API.
-   **`frontend/`**: A Next.js application for the user interface.

Both applications have their own `vercel.json` files, with a root `vercel.json` attempting to orchestrate the deployment of both.

## 2. Vercel Configuration Analysis

### 2.1. Root `vercel.json`

```json
{
  "version": 2,
  "builds": [
    {
      "src": "backend/main.py",
      "use": "@vercel/python"
    },
    {
      "src": "frontend/package.json",
      "use": "@vercel/next"
    }
  ],
  "rewrites": [
    {
      "source": "/api/v1/(.*)",
      "destination": "/backend/main.py"
    },
    {
      "source": "/(.*)",
      "destination": "/frontend/$1"
    }
  ]
}
```

**Observations:**

-   The `builds` section correctly identifies both the backend (`main.py`) and frontend (`package.json`) for their respective Vercel build processes.
-   The `rewrites` section attempts to route API requests starting with `/api/v1/` to the backend and all other requests to the frontend.

### 2.2. Backend `vercel.json` (`backend/vercel.json`)

```json
{
 "builds": [{ "src": "main.py", "use": "@vercel/python" }],
 "rewrites": [{ "source": "/(.*)", "destination": "/main.py" }]
}
```

**Observations:**

-   This `vercel.json` within the `backend` directory is largely redundant. The root `vercel.json` already specifies how to build and route the backend. Having a separate `vercel.json` in a sub-directory of a monorepo can lead to confusion or unintended behavior, especially if the root configuration is meant to be authoritative.

## 3. Frontend API Integration Analysis

Upon inspecting the `frontend/src` directory, particularly `frontend/src/lib/api.ts` and `frontend/src/hooks/useAuth.ts`, and searching for common API call patterns (`fetch`, `axios`, `API_URL`, `BASE_URL`), no direct API integration was found. The `frontend/src/app/(auth)/signup/page.tsx` confirms this, showing a placeholder `console.log` and `setTimeout` instead of an actual API call to the backend.

This indicates that the frontend is not yet connected to the backend API for user authentication or other functionalities.

## 4. Identified DevOps Issues

1.  **Redundant Backend Vercel Configuration:** The `backend/vercel.json` file is unnecessary and can be removed, as the root `vercel.json` already handles the backend deployment.
2.  **Missing Frontend API Integration:** The frontend application does not currently make actual API calls to the backend. The signup form, for instance, uses a mock delay instead of interacting with the FastAPI backend.

## 5. Proposed Solutions

### 5.1. Streamline Vercel Configuration

To simplify and correctly configure the Vercel deployment for the monorepo, the `backend/vercel.json` file should be removed. The root `vercel.json` is sufficient for defining the build and rewrite rules for both the frontend and backend.

**Action:** Remove `/home/ubuntu/luviio.in/backend/vercel.json`.

### 5.2. Connect Frontend to Backend API

To establish the connection between the Next.js frontend and the FastAPI backend, the following steps are proposed:

1.  **Define API Base URL:** Create an environment variable in the Next.js project (e.g., `NEXT_PUBLIC_API_BASE_URL`) to store the base URL of the backend API. This will allow for easy switching between development (e.g., `http://localhost:8000`) and production (e.g., `https://your-vercel-app.vercel.app/api/v1`).
2.  **Implement API Client:** Create a utility file (e.g., `frontend/src/lib/api.ts`) to handle API requests. This could involve using `fetch` or a library like `axios` to make HTTP requests to the backend.
3.  **Integrate API Calls in Frontend Components:** Modify components like `frontend/src/app/(auth)/signup/page.tsx` to use the API client to send user data to the backend's `/api/v1/users/signup` endpoint.

**Example Implementation for `frontend/src/lib/api.ts` (using `fetch`):**

```typescript
// frontend/src/lib/api.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

export async function signupUser(userData: any) {
  const response = await fetch(`${API_BASE_URL}/users/signup`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(userData),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Signup failed');
  }

  return response.json();
}
```

**Example Integration in `frontend/src/app/(auth)/signup/page.tsx`:**

```typescript
// src/app/(auth)/signup/page.tsx (relevant changes)

import { signupUser } from '@/lib/api'; // Import the new API function

// ... inside handleSignup function

  try {
    const response = await signupUser({ name, email, password });
    console.log("Signup successful:", response);
    alert(`Account created successfully for ${name}!`);
    // Optionally, redirect to login page or dashboard
  } catch (err: any) {
    setError(err.message || 'An unexpected error occurred.');
  } finally {
    setIsLoading(false);
  }

// ... rest of the component
```

These changes will ensure that the frontend correctly communicates with the backend API, completing the monorepo integration. 

## References

[1] Vercel Monorepos: [https://vercel.com/docs/projects/monorepos](https://vercel.com/docs/projects/monorepos)
[2] Next.js Environment Variables: [https://nextjs.org/docs/pages/building-your-application/configuring/environment-variables](https://nextjs.org/docs/pages/building-your-application/configuring/environment-variables)
[3] FastAPI Documentation: [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)
