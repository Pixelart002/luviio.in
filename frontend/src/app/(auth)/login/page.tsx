// src/app/(auth)/login/page.tsx
'use client'; // Client Component kyunki hume user input (state) capture karna hai

import React, { useState } from 'react';
import { Button } from '@/components/ui/Button';
import Link from 'next/link';

export default function LoginPage() {
 // TypeScript aur State: TS ko pata hai yeh string hain
 const [email, setEmail] = useState < string > ('');
 const [password, setPassword] = useState < string > ('');
 const [isLoading, setIsLoading] = useState < boolean > (false);
 
 // Form Submit Handler (TS Event typing)
 const handleLogin = async (e: React.FormEvent < HTMLFormElement > ) => {
  e.preventDefault(); // Page refresh hone se roko
  setIsLoading(true);
  
  // Abhi ke liye hum sirf console mein check kar rahe hain. 
  // Baad mein yahan FastAPI ko request jayegi!
  console.log("Login Request Sent:", { email, password });
  
  // Fake delay to show loading button animation
  setTimeout(() => {
   setIsLoading(false);
   alert(`Login attempt for ${email}`);
  }, 1500);
 };
 
 return (
  <div className="flex min-h-screen items-center justify-center bg-surface-muted p-4">
      <div className="w-full max-w-md bg-white p-8 rounded-xl shadow-md border border-slate-200">
        
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Welcome Back</h1>
          <p className="text-slate-500 mt-2">Sign in to your Luviio Store</p>
        </div>

        {/* Form connected to React State */}
        <form onSubmit={handleLogin} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)} // State update
              className="w-full px-4 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-colors"
              placeholder="you@example.com"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)} // State update
              className="w-full px-4 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-colors"
              placeholder="••••••••"
              required
            />
          </div>

          {/* Hamara CDUI Button with Loading state */}
          <Button 
            type="submit" 
            variant="primary" 
            className="w-full" 
            size="lg"
            isLoading={isLoading}
          >
            {isLoading ? "Signing in..." : "Sign In"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          Don't have an account?{' '}
          <Link href="/signup" className="text-brand-500 font-semibold hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </div>
 );
}