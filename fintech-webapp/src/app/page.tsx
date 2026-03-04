export default function SplashScreen() {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen bg-[#0f172a] text-white relative overflow-hidden">
      
      {/* Background Decorative Remix Icons (Subtle & Faded) */}
      <i className="ri-coin-fill absolute top-16 left-12 text-7xl text-blue-500/10 -rotate-12"></i>
      <i className="ri-safe-2-fill absolute bottom-24 right-12 text-8xl text-blue-500/10 rotate-12"></i>
      <i className="ri-line-chart-fill absolute top-24 right-20 text-6xl text-blue-500/10 rotate-6"></i>
      <i className="ri-wallet-3-fill absolute bottom-32 left-16 text-6xl text-blue-500/10 -rotate-6"></i>

      {/* Main Glowing Logo */}
      <div className="relative z-10 flex items-center justify-center w-28 h-28 bg-gradient-to-tr from-blue-600 to-indigo-500 rounded-[2rem] shadow-[0_0_60px_rgba(37,99,235,0.6)] mb-6 animate-pulse">
        <i className="ri-fingerprint-line text-7xl text-white"></i>
      </div>

      {/* Brand Name */}
      <h1 className="z-10 text-5xl font-extrabold tracking-tight mb-2 text-transparent bg-clip-text bg-gradient-to-b from-white to-gray-400">
        FinSecure
      </h1>

      {/* Loading Status with Spinning Remix Icon */}
      <div className="z-10 mt-10 flex items-center gap-3 text-blue-400 font-semibold tracking-widest uppercase text-sm bg-blue-900/30 px-6 py-3 rounded-full border border-blue-500/20 shadow-inner">
        <i className="ri-loader-5-line text-2xl animate-spin"></i>
        <span>Initializing Vault...</span>
      </div>

    </main>
  );
}
