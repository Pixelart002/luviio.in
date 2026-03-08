import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

// Optimize font loading with Next.js
const inter = Inter({
 subsets: ['latin'],
 variable: '--font-inter',
 display: 'swap',
})

// SEO & Metadata (Next.js 14 Native)
export const metadata: Metadata = {
 title: 'Enterprise ERP System',
 description: 'Next-gen scalable ERP built with Next.js and FastAPI',
}

export default function RootLayout({
 children,
}: {
 children: React.ReactNode
}) {
 return (
  <html lang="en" className={inter.variable}>
      {/* h-full aur min-h-screen ensure karte hain ki sidebar aur main content 
        height stretch karein, jo ERP layouts (Dashboards) ke liye zaruri hai.
      */}
      <body className="h-full min-h-screen flex flex-col">
        {/* Yahan future mein hum Navbar aur Sidebar layouts inject karenge */}
        <main className="flex-1">
          {children}
        </main>
      </body>
    </html>
 )
}