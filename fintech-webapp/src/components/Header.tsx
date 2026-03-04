"use client";
import { useState, useEffect } from 'react';
import Link from 'next/link';
import Drawer from './Drawer';
import { useFeatureFlags } from '../lib/hypertune';

export default function Header() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const flags = useFeatureFlags();

  // Dynamic Scroll Listener
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <>
      {flags.enablePromoBanner && (
        <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white text-xs sm:text-sm font-medium text-center py-2.5 px-4 shadow-md">
          🎉 Get $50 bonus on your first international transfer! <Link href="/signup" className="underline font-bold ml-1 hover:text-blue-200">Claim Now</Link>
        </div>
      )}

      {/* Dynamic Navbar: Changes background on scroll */}
      <nav className={`sticky top-0 z-30 transition-all duration-300 ${scrolled ? 'bg-[#0f172a]/85 backdrop-blur-lg border-b border-slate-800/80 shadow-lg' : 'bg-transparent border-transparent pt-2'}`}>
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-tr from-blue-600 to-indigo-500 rounded-xl flex items-center justify-center shadow-lg shadow-blue-600/30">
              <i className="ri-fingerprint-line text-2xl text-white"></i>
            </div>
            <span className="text-xl sm:text-2xl font-bold tracking-wide text-white">FinSecure</span>
          </div>
          
          <div className="hidden lg:flex items-center gap-8">
            <Link href="/dashboard" className="text-sm font-semibold text-slate-300 hover:text-white transition-colors">Personal</Link>
            <Link href="/business" className="text-sm font-semibold text-slate-300 hover:text-white transition-colors">Business</Link>
            <Link href="/login" className="text-sm font-semibold text-slate-300 hover:text-white transition-colors">Sign In</Link>
            <Link href="/login" className="px-6 py-2.5 bg-white text-slate-900 hover:bg-slate-200 text-sm font-bold rounded-xl transition-all shadow-[0_0_15px_rgba(255,255,255,0.1)]">
              Open Account
            </Link>
          </div>

          <button className="lg:hidden p-2 text-slate-300 hover:text-white bg-slate-800/50 rounded-lg" onClick={() => setIsDrawerOpen(true)}>
            <i className="ri-menu-4-line text-2xl sm:text-3xl"></i>
          </button>
        </div>
      </nav>

      <Drawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} />
    </>
  );
}
