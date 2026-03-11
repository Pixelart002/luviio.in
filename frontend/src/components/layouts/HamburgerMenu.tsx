// src/components/layouts/HamburgerMenu.tsx
'use client'; // Kyunki yahan click event (useState) chalega

import React, { useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/Button';
import { Menu, X } from 'lucide-react';

export default function HamburgerMenu() {
 const [isOpen, setIsOpen] = useState(false);
 
 const toggleMenu = () => setIsOpen(!isOpen);
 
 return (
  <div className="md:hidden flex items-center">
      {/* Menu / Close Icon */}
      <button onClick={toggleMenu} className="text-slate-600 hover:text-brand-500 focus:outline-none p-2">
        {isOpen ? <X size={28} /> : <Menu size={28} />}
      </button>

      {/* Dropdown List */}
      {isOpen && (
        <div className="absolute top-16 left-0 w-full border-b border-slate-200 bg-white shadow-md z-40">
          <div className="px-4 pt-2 pb-6 space-y-3 flex flex-col">
            <Link href="/" onClick={toggleMenu} className="block px-3 py-2 text-base font-medium text-slate-700 hover:text-brand-500 hover:bg-slate-50 rounded-md">Shop</Link>
            <div className="border-t border-slate-100 my-2"></div>
            <Button variant="ghost" className="w-full justify-start text-base">Cart (0)</Button>
            <Link href="/login" onClick={toggleMenu} className="block w-full">
              <Button variant="primary" className="w-full justify-center">Login</Button>
            </Link>
          </div>
        </div>
      )}
    </div>
 );
}