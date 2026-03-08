// src/app/dashboard/layout.tsx
import React from 'react';

// SEO/Meta data for the dashboard section
export const metadata = {
 title: 'Dashboard | ERP System',
 description: 'Main dashboard overview',
};

export default function DashboardLayout({
 children,
}: {
 children: React.ReactNode;
}) {
 return (
  <div className="flex h-screen overflow-hidden bg-surface-muted text-slate-800">
      
      {/* 🟢 LEFT SIDEBAR (Future CDUI Component) */}
      <aside className="w-64 bg-surface-dark text-white hidden md:flex flex-col shadow-lg z-20">
        <div className="h-16 flex items-center px-6 border-b border-slate-700">
          <span className="text-xl font-bold tracking-wider">ERP<span className="text-brand-500">PRO</span></span>
        </div>
        <nav className="flex-1 p-4 overflow-y-auto">
          {/* Yahan hum baad mein navigation links dalenge */}
          <p className="text-sm text-slate-400">Navigation Menu Placeholder</p>
        </nav>
      </aside>

      {/* 🔵 MAIN CONTENT AREA */}
      <div className="flex flex-col flex-1 w-full min-w-0">
        
        {/* 🟠 TOP HEADER */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 shadow-sm z-10">
          <h1 className="text-lg font-semibold text-slate-800">Overview</h1>
          <div className="flex items-center space-x-4">
            {/* Future Avatar/Logout logic */}
            <div className="h-8 w-8 rounded-full bg-brand-500 text-white flex items-center justify-center font-bold text-sm">
              PM
            </div>
          </div>
        </header>

        {/* 🟣 ACTUAL PAGE CONTENT (e.g., page.tsx will render here inside {children}) */}
        <main className="flex-1 overflow-y-auto p-6 md:p-8">
          <div className="max-w-7xl mx-auto">
            {children}
          </div>
        </main>

      </div>
    </div>
 );
}