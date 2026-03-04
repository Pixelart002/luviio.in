"use client";
import { useState } from 'react';
import Link from 'next/link';
import Drawer from './Drawer';
import { useFeatureFlags } from '../lib/hypertune';

export default function Header() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const flags = useFeatureFlags();

  return (
    <>
      {/* Feature Flag: Promo Banner */}
      {flags.enablePromoBanner && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-xs md:text-sm font-medium text-center py-2 px-4">
          🎉 Get $50 bonus on your first international transfer! <Link href="/signup" className="underline font-bold ml-1">Claim Now</Link>
        </div>
      )}

      <nav className="sticky top-0 z-30 bg-[#0f172a]/80 backdrop-blur-md border-b border-slate-800/60">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-tr from-blue-600 to-indigo-500 rounded-xl flex items-center justify-center shadow-lg shadow-blue-600/20">
              <i className="ri-fingerprint-line text-2xl text-white"></i>
            </div>
            <span className="text-xl font-bold tracking-wide text-white">FinSecure</span>
          </div>
          
          <div className="hidden md:flex items-center gap-8">
            <Link href="/dashboard" className="text-sm font-medium text-slate-300 hover:text-white transition-colors">Personal</Link>
            <Link href="/business" className="text-sm font-medium text-slate-300 hover:text-white transition-colors">Business</Link>
            <Link href="/login" className="text-sm font-medium text-slate-300 hover:text-white transition-colors">Sign In</Link>
            <Link href="/login" className="px-5 py-2.5 bg-white text-slate-900 hover:bg-slate-200 text-sm font-bold rounded-xl transition-all shadow-md">
              Open Account
            </Link>
          </div>

          <button className="md:hidden text-slate-300 hover:text-white" onClick={() => setIsDrawerOpen(true)}>
            <i className="ri-menu-4-line text-3xl"></i>
          </button>
        </div>
      </nav>

      <Drawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} />
    </>
  );
}
