export default function Dashboard() {
  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto">
      <header className="mb-10">
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Welcome back! Here's your financial summary.</p>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <h2 className="text-gray-500 text-sm font-medium mb-1">Total Balance</h2>
          <p className="text-3xl font-bold text-gray-900">$124,563.00</p>
        </div>
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <h2 className="text-gray-500 text-sm font-medium mb-1">Monthly Income</h2>
          <p className="text-3xl font-bold text-gray-900">$8,250.00</p>
        </div>
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <h2 className="text-gray-500 text-sm font-medium mb-1">Monthly Expenses</h2>
          <p className="text-3xl font-bold text-gray-900">$3,410.00</p>
        </div>
      </div>
    </div>
  )
}