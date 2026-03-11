// src/components/layouts/DesktopMenu.tsx
import React from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/Button';

export default function DesktopMenu() {
 return (
  <div className="hidden md:flex items-center gap-6">
      <Link href="/" className="text-sm font-medium text-slate-600 hover:text-brand-500 transition-colors">Shop</Link>
      <div className="w-px h-6 bg-slate-200"></div> {/* Line divider */}
      <Button variant="ghost" size="sm">Cart (0)</Button>
      <Link href="/login">
        <Button variant="primary" size="sm">Login</Button>
      </Link>
    </div>
 );
}