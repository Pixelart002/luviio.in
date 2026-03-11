// src/app/page.tsx
import { Button } from '@/components/ui/Button';
import Link from 'next/link';

export default function StoreFront() {
  return (
    <div className="flex min-h-screen flex-col bg-surface-light">
      
      {/* 🚀 Navigation Bar (Temporary inline for now) */}
      <nav className="w-full border-b border-slate-200 p-4 px-8 flex justify-between items-center bg-white shadow-sm">
        <div className="text-2xl font-bold text-slate-900 tracking-tight">
          LUVIIO<span className="text-brand-500">.</span>
        </div>
        <div className="flex gap-4">
          <Button variant="ghost" size="sm">Cart (0)</Button>
          
          {/* ✅ Sirf ek sahi Link wala Login Button */}
          <Link href="/login">
            <Button variant="primary" size="sm">Login</Button>
          </Link>
        </div>
      </nav>

      {/* 🛍️ Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <div className="max-w-3xl space-y-8">
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-slate-900">
            Elevate Your Everyday <br/>
            <span className="text-brand-500 text-4xl md:text-6xl">Premium Collection</span>
          </h1>
          
          <p className="text-lg md:text-xl leading-relaxed text-slate-600 max-w-2xl mx-auto">
            Discover our latest arrivals. Designed for comfort, engineered for style. Upgrade your wardrobe with Luviio.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
            <Button size="lg" variant="primary" className="w-full sm:w-auto px-8">
              Shop Now
            </Button>
            <Button size="lg" variant="outline" className="w-full sm:w-auto px-8">
              View Categories
            </Button>
          </div>
        </div>
      </main>

      {/* 🏁 Simple Footer */}
      <footer className="w-full border-t border-slate-200 p-6 text-center text-slate-500 text-sm bg-surface-muted">
        © 2026 Luviio Store. All rights reserved. Built with Next.js & FastAPI.
      </footer>
    </div>
  );
}