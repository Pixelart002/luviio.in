import Link from 'next/link';

export default function Hero() {
  return (
    <section className="container mx-auto px-4 sm:px-6 lg:px-8 pt-16 sm:pt-24 pb-16 sm:pb-24 text-center relative">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[20rem] sm:w-[30rem] lg:w-[40rem] h-[20rem] sm:h-[30rem] lg:h-[40rem] bg-blue-600/10 blur-[120px] rounded-full pointer-events-none"></div>
      
      <div className="relative z-10">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs sm:text-sm font-bold uppercase tracking-widest mb-6 sm:mb-8 shadow-[0_0_20px_rgba(59,130,246,0.1)]">
          <i className="ri-flashlight-fill"></i> Lightning Fast Banking
        </div>
        
        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight mb-6 sm:mb-8 bg-clip-text text-transparent bg-gradient-to-b from-white via-slate-200 to-slate-500 leading-tight">
          The Future of <br className="hidden sm:block" /> Secure Finance.
        </h1>
        
        <p className="text-slate-400 text-base sm:text-lg lg:text-xl max-w-2xl mx-auto mb-10 sm:mb-12 leading-relaxed px-2">
          Manage your digital assets, track real-time transactions, and secure your financial future with military-grade encryption.
        </p>
        
        <div className="flex flex-col sm:flex-row justify-center items-center gap-4 sm:gap-6 px-4 sm:px-0">
          <Link href="/dashboard" className="w-full sm:w-auto px-8 py-4 bg-white text-slate-900 hover:bg-slate-200 font-bold rounded-xl transition-all flex items-center justify-center gap-2 shadow-lg hover:shadow-xl hover:-translate-y-0.5">
            Access Dashboard <i className="ri-arrow-right-line"></i>
          </Link>
          <Link href="/login" className="w-full sm:w-auto px-8 py-4 bg-slate-800 text-white hover:bg-slate-700 font-bold rounded-xl transition-all flex items-center justify-center gap-2 border border-slate-700 hover:border-slate-600">
            Open Account
          </Link>
        </div>
      </div>
    </section>
  );
}
