"use client";
import Link from 'next/link';
import { useFeatureFlags } from '../lib/hypertune';

export default function Drawer({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const flags = useFeatureFlags();

  return (
    <>
      {/* Background Overlay */}
      <div className={`fixed inset-0 bg-black/60 backdrop-blur-sm z-40 transition-opacity duration-300 ${isOpen ? 'opacity-100 visible' : 'opacity-0 invisible'}`} onClick={onClose}></div>
      
      {/* Drawer Panel */}
      <div className={`fixed top-0 right-0 h-full w-72 bg-slate-900 border-l border-slate-800 z-50 transform transition-transform duration-300 flex flex-col ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}>
        <div className="p-6 border-b border-slate-800 flex items-center justify-between">
          <span className="text-xl font-bold text-white">Menu</span>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <i className="ri-close-line text-2xl"></i>
          </button>
        </div>
        
        <div className="flex flex-col p-6 gap-6 flex-1">
          <Link href="/dashboard" className="text-lg font-medium text-slate-300 hover:text-white flex items-center gap-3"><i className="ri-dashboard-line"></i> Dashboard</Link>
          <Link href="/transfers" className="text-lg font-medium text-slate-300 hover:text-white flex items-center gap-3"><i className="ri-exchange-dollar-line"></i> Transfers</Link>
          
          {/* Feature Flag: Crypto */}
          {flags.enableCryptoFeature && (
            <Link href="/crypto" className="text-lg font-medium text-blue-400 hover:text-blue-300 flex items-center gap-3"><i className="ri-btc-line"></i> Crypto Trading <span className="text-[10px] bg-blue-600/20 text-blue-400 px-2 py-0.5 rounded-full uppercase">New</span></Link>
          )}
        </div>

        <div className="p-6 border-t border-slate-800">
          <Link href="/login" className="w-full block text-center px-5 py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition-all">
            Sign In
          </Link>
        </div>
      </div>
    </>
  );
}
