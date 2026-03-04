export default function Features() {
  // Dynamic Data Array - Easily scalable
  const featureList = [
    {
      id: 1,
      icon: 'ri-send-plane-fill',
      title: 'Instant Transfers',
      desc: 'Send and receive money globally in milliseconds with zero hidden fees.',
      colorClass: 'text-blue-400 group-hover:bg-blue-500',
      bgClass: 'bg-blue-500/10',
      borderHover: 'hover:border-blue-500/50'
    },
    {
      id: 2,
      icon: 'ri-shield-check-fill',
      title: 'Ironclad Security',
      desc: 'Your funds are protected by end-to-end encryption and biometric authentication.',
      colorClass: 'text-green-400 group-hover:bg-green-500',
      bgClass: 'bg-green-500/10',
      borderHover: 'hover:border-green-500/50'
    },
    {
      id: 3,
      icon: 'ri-pie-chart-2-fill',
      title: 'Smart Analytics',
      desc: 'Track your expenses and grow your wealth with AI-driven financial insights.',
      colorClass: 'text-purple-400 group-hover:bg-purple-500',
      bgClass: 'bg-purple-500/10',
      borderHover: 'hover:border-purple-500/50'
    }
  ];

  return (
    <section className="container mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-24">
      <div className="text-center mb-16">
        <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">Why Choose FinSecure?</h2>
        <p className="text-slate-400 max-w-2xl mx-auto">Everything you need to manage your money smartly and securely.</p>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
        {featureList.map((feature) => (
          <div key={feature.id} className={`p-8 rounded-3xl bg-slate-800/30 border border-slate-700/50 transition-all duration-300 hover:-translate-y-2 group ${feature.borderHover} shadow-lg hover:shadow-2xl`}>
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-6 transition-colors duration-300 group-hover:text-white ${feature.bgClass} ${feature.colorClass}`}>
              <i className={`${feature.icon} text-3xl`}></i>
            </div>
            <h3 className="text-xl font-bold text-white mb-3 tracking-wide">{feature.title}</h3>
            <p className="text-slate-400 leading-relaxed text-sm sm:text-base">{feature.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
