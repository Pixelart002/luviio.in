export default function Dashboard() {
  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto">
      <header className="mb-10">
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Welcome back! Here's your financial summary.</p>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        {/* Balance Card */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex justify-between items-start mb-6">
            <div className="w-12 h-12 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center">
              <i className="ri-wallet-3-line text-2xl"></i>
            </div>
            <span className="text-sm font-semibold text-green-700 bg-green-50 px-2.5 py-1 rounded-md flex items-center gap-1">
              <i className="ri-arrow-up-line"></i> 2.4%
            </span>
          </div>
          <h2 className="text-gray-500 text-sm font-medium mb-1">Total Balance</h2>
          <p className="text-3xl md:text-4xl font-bold text-gray-900">$124,563.00</p>
        </div>

        {/* Income Card */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex justify-between items-start mb-6">
            <div className="w-12 h-12 bg-green-50 text-green-600 rounded-full flex items-center justify-center">
              <i className="ri-arrow-right-down-line text-2xl"></i>
            </div>
          </div>
          <h2 className="text-gray-500 text-sm font-medium mb-1">Monthly Income</h2>
          <p className="text-3xl font-bold text-gray-900">$8,250.00</p>
        </div>

        {/* Expenses Card */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex justify-between items-start mb-6">
            <div className="w-12 h-12 bg-red-50 text-red-600 rounded-full flex items-center justify-center">
              <i className="ri-arrow-right-up-line text-2xl"></i>
            </div>
          </div>
          <h2 className="text-gray-500 text-sm font-medium mb-1">Monthly Expenses</h2>
          <p className="text-3xl font-bold text-gray-900">$3,410.00</p>
        </div>
      </div>
      
      {/* Quick Actions (Placeholder) */}
      <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
        <h3 className="font-bold text-lg text-gray-900 mb-4">Quick Transfer</h3>
        <p className="text-gray-500 text-sm mb-4">Send money securely to anyone in your contacts.</p>
        <button className="bg-blue-600 text-white px-5 py-2.5 rounded-xl font-medium hover:bg-blue-700 transition">
          <i className="ri-send-plane-fill mr-2"></i> Send Money
        </button>
      </div>
    </div>
  )
}