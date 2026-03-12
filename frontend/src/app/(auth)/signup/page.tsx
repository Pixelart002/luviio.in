// src/app/(auth)/signup/page.tsx
'use client';

import React, { useState } from 'react';
import { Button } from '@/components/ui/Button';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';

export default function SignupPage() {
  // TypeScript States for the form
  const [name, setName] = useState<string>('');
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [confirmPassword, setConfirmPassword] = useState<string>('');
  const [localError, setLocalError] = useState<string>('');
  
  // Use the auth hook for signup functionality
  const { isLoading, error: authError, signup } = useAuth();
  const router = useRouter();

  // Form Submit Handler
  const handleSignup = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLocalError(''); // Clear previous errors

    // Basic Frontend Validation
    if (password !== confirmPassword) {
      setLocalError('Passwords do not match!');
      return;
    }

    if (password.length < 6) {
      setLocalError('Password must be at least 6 characters long!');
      return;
    }

    try {
      // Call the signup function from useAuth hook
      await signup(name, email, password);
      
      // On successful signup, redirect to login page
      router.push('/login?signup=success');
    } catch (err: any) {
      // Error is already set in the auth hook, but we can handle it here if needed
      console.error('Signup error:', err);
    }
  };

  // Determine which error to display
  const displayError = localError || authError;

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted p-4 py-12">
      <div className="w-full max-w-md bg-white p-8 rounded-xl shadow-md border border-slate-200">
        
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Create Account</h1>
          <p className="text-slate-500 mt-2">Join Luviio Store today</p>
        </div>

        {/* Display error if it exists */}
        {displayError && (
          <div className="mb-4 p-3 bg-red-50 text-red-600 border border-red-200 rounded-md text-sm text-center">
            {displayError}
          </div>
        )}

        <form onSubmit={handleSignup} className="space-y-5">
          {/* Full Name Field */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Full Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-colors"
              placeholder="John Doe"
              required
              disabled={isLoading}
            />
          </div>

          {/* Email Field */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-colors"
              placeholder="you@example.com"
              required
              disabled={isLoading}
            />
          </div>

          {/* Password Field */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-colors"
              placeholder="••••••••"
              required
              minLength={6}
              disabled={isLoading}
            />
          </div>

          {/* Confirm Password Field */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Confirm Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-colors"
              placeholder="••••••••"
              required
              disabled={isLoading}
            />
          </div>

          <Button 
            type="submit" 
            variant="primary" 
            className="w-full mt-2" 
            size="lg"
            isLoading={isLoading}
            disabled={isLoading}
          >
            {isLoading ? "Creating account..." : "Create Account"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          Already have an account?{' '}
          <Link href="/login" className="text-brand-500 font-semibold hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
