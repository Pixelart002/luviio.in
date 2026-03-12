// frontend/src/hooks/useAuth.ts
'use client';

import { useState, useCallback, useEffect } from 'react';
import { signupUser, loginUser, logoutUser, getCurrentUser } from '@/lib/api';

interface User {
  id: string;
  name: string;
  email: string;
  created_at: string;
  is_active: boolean;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
}

/**
 * Custom hook for managing user authentication
 * Handles signup, login, logout, and session persistence
 */
export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>({
    user: null,
    token: null,
    isLoading: false,
    error: null,
  });

  // Load token from localStorage on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('auth_token');
    if (savedToken) {
      setAuthState((prev) => ({ ...prev, token: savedToken }));
    }
  }, []);

  /**
   * Handle user signup
   */
  const signup = useCallback(
    async (name: string, email: string, password: string) => {
      setAuthState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        const response = await signupUser({ name, email, password });
        setAuthState((prev) => ({
          ...prev,
          user: response,
          isLoading: false,
        }));
        return response;
      } catch (err: any) {
        const errorMessage = err.message || 'Signup failed';
        setAuthState((prev) => ({
          ...prev,
          error: errorMessage,
          isLoading: false,
        }));
        throw err;
      }
    },
    []
  );

  /**
   * Handle user login
   */
  const login = useCallback(
    async (email: string, password: string) => {
      setAuthState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        const response = await loginUser({ email, password });
        const token = response.access_token || response.token;

        if (token) {
          localStorage.setItem('auth_token', token);
        }

        setAuthState((prev) => ({
          ...prev,
          user: response.user || response,
          token: token,
          isLoading: false,
        }));
        return response;
      } catch (err: any) {
        const errorMessage = err.message || 'Login failed';
        setAuthState((prev) => ({
          ...prev,
          error: errorMessage,
          isLoading: false,
        }));
        throw err;
      }
    },
    []
  );

  /**
   * Handle user logout
   */
  const logout = useCallback(async () => {
    setAuthState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      if (authState.token) {
        await logoutUser(authState.token);
      }

      localStorage.removeItem('auth_token');
      setAuthState({
        user: null,
        token: null,
        isLoading: false,
        error: null,
      });
    } catch (err: any) {
      const errorMessage = err.message || 'Logout failed';
      setAuthState((prev) => ({
        ...prev,
        error: errorMessage,
        isLoading: false,
      }));
    }
  }, [authState.token]);

  /**
   * Fetch current user profile
   */
  const fetchCurrentUser = useCallback(async () => {
    if (!authState.token) return;

    setAuthState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const user = await getCurrentUser(authState.token);
      setAuthState((prev) => ({
        ...prev,
        user,
        isLoading: false,
      }));
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to fetch user';
      setAuthState((prev) => ({
        ...prev,
        error: errorMessage,
        isLoading: false,
      }));
    }
  }, [authState.token]);

  return {
    ...authState,
    signup,
    login,
    logout,
    fetchCurrentUser,
    isAuthenticated: !!authState.token,
  };
}
