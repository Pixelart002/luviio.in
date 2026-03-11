// src/app/layout.tsx
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

// 🚀 Naye modular components import kar rahe hain
import Header from '@/components/layouts/Header';
import Footer from '@/components/layouts/Footer';

const inter = Inter({
 subsets: ['latin'],
 variable: '--font-inter',
 display: 'swap',
});

export const metadata: Metadata = {
 title: 'Luviio | Premium E-commerce',
 description: 'Next-gen scalable ERP built with Next.js and FastAPI',
};

export default function RootLayout({
 children,
}: {
 children: React.ReactNode
}) {
 return (
  <html lang="en" className={inter.variable}>
      <body className="h-full min-h-screen flex flex-col bg-surface-light">
        
        {/* 1. Global Header (Jiske andar apne aap desktop aur mobile menu hain) */}
        <Header />

        {/* 2. Main Page Content (Hero section, forms, etc.) */}
        <main className="flex-1 flex flex-col">
          {children}
        </main>

        {/* 3. Global Footer */}
        <Footer />
        
      </body>
    </html>
 );
}