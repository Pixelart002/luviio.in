import Link from 'next/link';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0f172a] text-white selection:bg-blue-500/30">
      
      {/* Navbar */}
      <nav className="container mx-auto px-6 py-6 flex items-center justify-between border-b border-slate-800/60 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-tr from-blue-600 to-indigo-500 rounded-xl flex items-center justify-center shadow-lg shadow-blue-600/20">
            <i className="ri-fingerprint-line text-2xl text-white"></i>
          </div>
          <span className="text-xl font-bold tracking-wide">FinSecure</span>
        </div>
        <div className="flex items-center gap-6">
          <Link href="/login" className="text-sm font-medium text-slate-300 hover:text-white transition-colors">
            Sign In
          </Link>
          <Link href="/login" className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-sm font-semibold rounded-lg shadow-lg shadow-blue-600/30 transition-all hidden md:block">
            Get Started
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="container mx-auto px-6 pt-24 pb-20 text-center relative">
        {/* Background Glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[30rem] h-[30rem] bg-blue-600/10 blur-[100px] rounded-full pointer-events-none"></div>

        <div className="relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold uppercase tracking-wider mb-8">
            <i className="ri-flashlight-fill"></i> Lightning Fast Banking
          </div>
          
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6 bg-clip-text text-transparent bg-gradient-to-b from-white to-slate-400">
            The Future of <br className="hidden md:block" /> Secure Finance.
          </h1>
          
          <p className="text-slate-400 text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed">
            Manage your digital assets, track real-time transactions, and secure your financial future with military-grade encryption.
          </p>
          
          <div className="flex flex-col sm:flex-row justify-center items-center gap-4">
            <Link href="/dashboard" className="px-8 py-4 bg-white text-slate-900 hover:bg-slate-200 font-bold rounded-xl transition-all flex items-center justify-center gap-2 w-full sm:w-auto">
              Access Dashboard <i className="ri-arrow-right-line"></i>
            </Link>
            <Link href="/login" className="px-8 py-4 bg-slate-800 text-white hover:bg-slate-700 font-bold rounded-xl transition-all flex items-center justify-center gap-2 w-full sm:w-auto border border-slate-700">
              Open Account
            </Link>
          </div>
        </div>
      </main>

      {/* Features Grid */}
      <section className="container mx-auto px-6 py-20 border-t border-slate-800/60">
        <div className="grid md:grid-cols-3 gap-8">
          
          {/* Feature 1 */}
          <div className="p-8 rounded-3xl bg-slate-800/30 border border-slate-700/50 hover:border-blue-500/50 transition-all hover:-translate-y-1 group">
            <div className="w-14 h-14 bg-blue-500/10 rounded-2xl flex items-center justify-center mb-6 text-blue-400 group-hover:bg-blue-500 group-hover:text-white transition-colors">
              <i className="ri-send-plane-fill text-3xl"></i>
            </div>
            <h3 className="text-xl font-bold mb-3">Instant Transfers</h3>
            <p className="text-slate-400 leading-relaxed">Send and receive money globally in milliseconds with zero hidden fees.</p>
          </div>

          {/* Feature 2 */}
          <div className="p-8 rounded-3xl bg-slate-800/30 border border-slate-700/50 hover:border-green-500/50 transition-all hover:-translate-y-1 group">
            <div className="w-14 h-14 bg-green-500/10 rounded-2xl flex items-center justify-center mb-6 text-green-400 group-hover:bg-green-500 group-hover:text-white transition-colors">
              <i className="ri-shield-check-fill text-3xl"></i>
            </div>
            <h3 className="text-xl font-bold mb-3">Ironclad Security</h3>
            <p className="text-slate-400 leading-relaxed">Your funds are protected by end-to-end encryption and biometric authentication.</p>
          </div>

          {/* Feature 3 */}
          <div className="p-8 rounded-3xl bg-slate-800/30 border border-slate-700/50 hover:border-purple-500/50 transition-all hover:-translate-y-1 group">
            <div className="w-14 h-14 bg-purple-500/10 rounded-2xl flex items-center justify-center mb-6 text-purple-400 group-hover:bg-purple-500 group-hover:text-white transition-colors">
              <i className="ri-pie-chart-2-fill text-3xl"></i>
            </div>
            <h3 className="text-xl font-bold mb-3">Smart Analytics</h3>
            <p className="text-slate-400 leading-relaxed">Track your expenses and grow your wealth with AI-driven financial insights.</p>
          </div>

        </div>
      </section>

    </div>
  );
}
