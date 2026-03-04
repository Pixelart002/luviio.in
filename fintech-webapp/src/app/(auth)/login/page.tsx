export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-8 text-center border border-gray-100">
        
        <div className="w-16 h-16 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mx-auto mb-6">
          <i className="ri-bank-card-line text-3xl"></i>
        </div>
        
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Welcome to FinSecure</h1>
        <p className="text-gray-500 mb-8">Secure access to your financial dashboard</p>
        
        {/* 'a' tag instead of Next/Link because we are leaving the app temporarily to go to Google via our API */}
        <a 
          href="/api/auth/login"
          className="flex items-center justify-center w-full bg-[#0f172a] text-white font-semibold py-3.5 px-4 rounded-xl hover:bg-gray-800 transition-colors gap-2"
        >
          <i className="ri-google-fill text-xl"></i>
          Continue with Google
        </a>
        
        <p className="mt-8 text-xs text-gray-400 flex items-center justify-center gap-1">
          <i className="ri-lock-fill"></i> Secured by industry-standard OAuth 2.0
        </p>
      </div>
    </div>
  )
}