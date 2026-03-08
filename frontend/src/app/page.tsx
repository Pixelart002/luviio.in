// src/app/page.tsx
import { Button } from '@/components/ui/Button';

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-6 bg-surface-muted">
      <div className="text-center space-y-6 max-w-2xl">
        {/* Brand Header */}
        <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-6xl">
          Luviio <span className="text-brand-500">Workspace</span>
        </h1>
        
        <p className="text-lg leading-8 text-slate-600">
          Enterprise Resource Planning System. Manage your business efficiently with our scalable Next.js and FastAPI architecture.
        </p>
        
        {/* Call to Actions using our CDUI Button */}
        <div className="flex items-center justify-center gap-x-4 pt-4">
          <Button size="lg" variant="primary">
            Enter Dashboard
          </Button>
          <Button size="lg" variant="outline">
            Admin Login
          </Button>
        </div>
        
        <p className="text-sm text-slate-400 mt-8">
          © 2026 Luviio.in. Secure Portal.
        </p>
      </div>
    </div>
  );
}