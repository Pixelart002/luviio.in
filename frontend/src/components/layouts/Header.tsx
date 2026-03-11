// src/components/layouts/Header.tsx
import React from 'react';
import Link from 'next/link';
import DesktopMenu from './DesktopMenu';
import HamburgerMenu from './HamburgerMenu';

export default function Header() {
 return (
  <header className="w-full border-b border-slate-200 bg-white shadow-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          
          {/* Logo */}
          <Link href="/" className="text-2xl font-bold text-slate-900 tracking-tight">
            LUVIIO<span className="text-brand-500">.</span>
          </Link>

          {/* Menus (Jo humne alag files mein banaye hain) */}
          <DesktopMenu />
          <HamburgerMenu />
          
        </div>
      </div>
    </header>
 );
}