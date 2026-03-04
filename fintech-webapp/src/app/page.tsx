import Link from 'next/link'

export default function HomePage() {
 return (
  <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 p-6 relative overflow-hidden">
      
      {/* Background Decoration */}
      <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-blue-300 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-2000"></div>

      <div className="text-center max-w-2xl relative z-10">
        <div className="w-20 h-20 bg-blue-50 text-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-8 shadow-sm border border-blue-100">
          <i className="ri-shield-check-fill text-4xl"></i>
        </div>
        
        <h1 className="text-5xl md:text-6xl font-extrabold text-gray-900 tracking-tight mb-6">
          The Future of <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-blue-400">Secure Finance</span>
        </h1>
        
        <p className="text-lg text-gray-600 mb-10 leading-relaxed">
          Manage your assets, track transactions, and securely authenticate with enterprise-grade protection. Built for the modern web.
        </p>
        
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/login"
            className="flex items-center justify-center gap-2 bg-[#0f172a] text-white px-8 py-4 rounded-xl font-semibold hover:bg-gray-800 transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5"
          >
            Access Dashboard <i className="ri-arrow-right-line"></i>
          </Link>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 bg-white text-gray-700 border border-gray-200 px-8 py-4 rounded-xl font-semibold hover:bg-gray-50 hover:text-gray-900 transition-all shadow-sm"
          >
            <i className="ri-github-fill text-xl"></i> View Source
          </a>
        </div>
      </div>
    </div>
 )
}