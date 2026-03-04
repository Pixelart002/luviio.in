export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-[#0f172a] text-white">
      <div className="relative flex items-center justify-center w-24 h-24 bg-blue-600 rounded-3xl mb-8 animate-pulse shadow-[0_0_40px_rgba(37,99,235,0.4)]">
        <i className="ri-shield-flash-fill text-6xl text-white"></i>
      </div>
      <h1 className="text-4xl font-extrabold tracking-tight mb-3">FinSecure</h1>
      <p className="text-blue-400 text-sm font-medium tracking-widest uppercase mt-2">
        <i className="ri-loader-4-line text-lg animate-spin inline-block mr-2"></i>
        System Ready
      </p>
    </main>
  )
}
