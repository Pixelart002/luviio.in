export default function Features() {
  return (
    <section className="container mx-auto px-6 py-20">
      <div className="grid md:grid-cols-3 gap-8">
        <div className="p-8 rounded-3xl bg-slate-800/30 border border-slate-700/50 hover:border-blue-500/50 transition-all hover:-translate-y-1 group">
          <div className="w-14 h-14 bg-blue-500/10 rounded-2xl flex items-center justify-center mb-6 text-blue-400 group-hover:bg-blue-500 group-hover:text-white transition-colors">
            <i className="ri-send-plane-fill text-3xl"></i>
          </div>
          <h3 className="text-xl font-bold text-white mb-3">Instant Transfers</h3>
          <p className="text-slate-400 leading-relaxed">Send and receive money globally in milliseconds with zero hidden fees.</p>
        </div>
        <div className="p-8 rounded-3xl bg-slate-800/30 border border-slate-700/50 hover:border-green-500/50 transition-all hover:-translate-y-1 group">
          <div className="w-14 h-14 bg-green-500/10 rounded-2xl flex items-center justify-center mb-6 text-green-400 group-hover:bg-green-500 group-hover:text-white transition-colors">
            <i className="ri-shield-check-fill text-3xl"></i>
          </div>
          <h3 className="text-xl font-bold text-white mb-3">Ironclad Security</h3>
          <p className="text-slate-400 leading-relaxed">Your funds are protected by end-to-end encryption and biometric authentication.</p>
        </div>
        <div className="p-8 rounded-3xl bg-slate-800/30 border border-slate-700/50 hover:border-purple-500/50 transition-all hover:-translate-y-1 group">
          <div className="w-14 h-14 bg-purple-500/10 rounded-2xl flex items-center justify-center mb-6 text-purple-400 group-hover:bg-purple-500 group-hover:text-white transition-colors">
            <i className="ri-pie-chart-2-fill text-3xl"></i>
          </div>
          <h3 className="text-xl font-bold text-white mb-3">Smart Analytics</h3>
          <p className="text-slate-400 leading-relaxed">Track your expenses and grow your wealth with AI-driven financial insights.</p>
        </div>
      </div>
    </section>
  );
}
