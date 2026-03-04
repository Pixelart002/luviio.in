"use client";
import Link from 'next/link';
import { useFeatureFlags } from '../lib/hypertune';

export default function Drawer({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const flags = useFeatureFlags();

  return (
    <>
      {/* Background Overlay */}
      <div className={`fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-40 transition-opacity duration-300 ${isOpen ? 'opacity-100 visible' : 'opacity-0 invisible'}`} onClick={onClose}></div>
      
      {/* Drawer Panel */}
      <div className={`fixed top-0 right-0 h-full w-[80%] max-w-sm bg-slate-900 border-l border-slate-800 z-50 transform transition-transform duration-300 flex flex-col ${isOpen ? 'translate-x-0 shadow-2xl' : 'translate-x-full'}`}>
        <div className="p-5 sm:p-6 border-b border-slate-800 flex items-center justify-between">
          <span className="text-xl font-bold text-white tracking-wide">Menu</span>
          <button onClick={onClose} className="p-2 bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-all">
            <i className="ri-close-line text-xl"></i>
          </button>
        </div>
        
        <div className="flex flex-col p-5 sm:p-6 gap-6 flex-1 overflow-y-auto">
          <Link href="/dashboard" className="text-lg font-medium text-slate-300 hover:text-blue-400 flex items-center gap-4 transition-colors"><i className="ri-dashboard-line text-xl"></i> Dashboard</Link>
          <Link href="/transfers" className="text-lg font-medium text-slate-300 hover:text-blue-400 flex items-center gap-4 transition-colors"><i className="ri-exchange-dollar-line text-xl"></i> Transfers</Link>
          
          {/* Feature Flag: Crypto */}
          {flags.enableCryptoFeature && (
            <Link href="/crypto" className="text-lg font-medium text-blue-400 hover:text-blue-300 flex items-center gap-4 transition-colors"><i className="ri-btc-line text-xl"></i> Crypto Trading <span className="text-[10px] bg-blue-600/20 text-blue-400 px-2.5 py-1 rounded-full uppercase font-bold tracking-wider ml-auto">New</span></Link>
          )}
        </div>

        <div className="p-5 sm:p-6 border-t border-slate-800 bg-slate-900/50">
          <Link href="/login" className="w-full flex justify-center items-center gap-2 px-5 py-3.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition-all shadow-lg shadow-blue-600/20">
            Sign In <i className="ri-arrow-right-line"></i>
          </Link>
        </div>
      </div>
    </>
  );
}
