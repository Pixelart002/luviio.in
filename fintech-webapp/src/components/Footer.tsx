"use client";
import Link from 'next/link';
import { useFeatureFlags } from '../lib/hypertune';

export default function Footer() {
  const flags = useFeatureFlags();

  return (
    <footer className="border-t border-slate-800/60 bg-[#0f172a] pt-12 sm:pt-16 pb-8">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col lg:flex-row justify-between items-center lg:items-start gap-8 lg:gap-6 text-center lg:text-left">
          
          <div className="flex flex-col items-center lg:items-start gap-3">
            <div className="flex items-center gap-3">
              <i className="ri-fingerprint-line text-2xl text-blue-500"></i>
              <span className="text-xl font-bold text-white">FinSecure</span>
            </div>
            <p className="text-slate-500 text-sm max-w-xs">Banking reimagined for the modern world. Fast, secure, and reliable.</p>
          </div>
          
          {flags.enableNewFooter ? (
            <div className="flex flex-wrap justify-center gap-x-8 gap-y-4 text-sm font-medium text-slate-400">
              <Link href="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link>
              <Link href="/terms" className="hover:text-white transition-colors">Terms of Service</Link>
              <Link href="/contact" className="hover:text-white transition-colors">Contact Us</Link>
              <Link href="/careers" className="hover:text-white transition-colors">Careers</Link>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Standard Footer Links</p>
          )}
        </div>
        
        <div className="mt-12 pt-8 border-t border-slate-800/50 flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="text-slate-500 text-sm">&copy; {new Date().getFullYear()} FinSecure Inc. All rights reserved.</p>
          <div className="flex gap-4">
            <a href="#" className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 hover:text-white hover:bg-blue-600 transition-all"><i className="ri-twitter-x-line"></i></a>
            <a href="#" className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 hover:text-white hover:bg-blue-600 transition-all"><i className="ri-linkedin-fill"></i></a>
          </div>
        </div>
      </div>
    </footer>
  );
}
