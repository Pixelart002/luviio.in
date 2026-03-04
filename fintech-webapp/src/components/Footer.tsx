"use client";
import Link from 'next/link';
import { useFeatureFlags } from '../lib/hypertune';

export default function Footer() {
  const flags = useFeatureFlags();

  return (
    <footer className="border-t border-slate-800/60 bg-[#0f172a] pt-16 pb-8">
      <div className="container mx-auto px-6">
        <div className="flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-3">
            <i className="ri-fingerprint-line text-2xl text-blue-500"></i>
            <span className="text-xl font-bold text-white">FinSecure</span>
          </div>
          
          {/* Feature Flag: New Footer Layout */}
          {flags.enableNewFooter ? (
            <div className="flex gap-6 text-sm text-slate-400">
              <Link href="/privacy" className="hover:text-white">Privacy Policy</Link>
              <Link href="/terms" className="hover:text-white">Terms of Service</Link>
              <Link href="/contact" className="hover:text-white">Contact Us</Link>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Standard Footer Links Here</p>
          )}
        </div>
        <div className="mt-8 text-center text-slate-500 text-sm">
          &copy; {new Date().getFullYear()} FinSecure Inc. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
