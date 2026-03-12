// frontend/src/lib/api.ts
// API client for communicating with the FastAPI backend

/**
 * Base URL for API requests
 * In development: http://localhost:8000/api/v1
 * In production: https://your-vercel-app.vercel.app/api/v1
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '/api/v1';

/**
 * Generic fetch wrapper with error handling
 */
async function apiCall<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API Error: ${response.status}`);
  }

  return response.json();
}

/**
 * User signup API call
 * Sends user registration data to the backend
 */
export async function signupUser(userData: {
  name: string;
  email: string;
  password: string;
}) {
  return apiCall('/users/signup', {
    method: 'POST',
    body: JSON.stringify(userData),
  });
}

/**
 * User login API call
 * Authenticates user and returns JWT token
 */
export async function loginUser(credentials: {
  email: string;
  password: string;
}) {
  return apiCall('/users/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  });
}

/**
 * Get current user profile
 * Requires authentication token
 */
export async function getCurrentUser(token: string) {
  return apiCall('/users/me', {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

/**
 * Logout user
 * Invalidates the user session
 */
export async function logoutUser(token: string) {
  return apiCall('/users/logout', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}
