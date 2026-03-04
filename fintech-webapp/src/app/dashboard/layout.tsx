import Link from 'next/link'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <aside className="w-20 md:w-64 bg-white border-r border-gray-200 flex flex-col transition-all">
        <div className="h-20 flex items-center justify-center md:justify-start md:px-6 border-b border-gray-100">
          <i className="ri-shield-flash-line text-blue-600 text-3xl"></i>
          <span className="hidden md:block ml-3 font-bold text-xl text-gray-900">FinSecure</span>
        </div>
        <nav className="flex-1 py-6 flex flex-col gap-2 px-3">
          <Link href="/dashboard" className="flex items-center gap-3 px-3 py-3.5 bg-blue-50 text-blue-700 rounded-xl">
            <i className="ri-dashboard-line text-xl"></i>
            <span className="hidden md:block font-medium">Overview</span>
          </Link>
        </nav>
      </aside>
      <main className="flex-1 overflow-y-auto w-full">
        {children}
      </main>
    </div>
  )
}