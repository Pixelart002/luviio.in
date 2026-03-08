// src/app/page.tsx
import Link from 'next/link';
import { Button } from '@/components/ui/Button';

export default function LandingPage() {
 return (
  <div className="min-h-screen flex flex-col items-center justify-center bg-surface-muted p-4">
      
      {/* Main Container */}
      <div className="max-w-md w-full text-center space-y-8">
        
        {/* Logo / Branding Section */}
        <div className="space-y-4">
          <div className="h-20 w-20 bg-brand-500 rounded-2xl mx-auto flex items-center justify-center shadow-lg transform transition-transform hover:scale-105">
            {/* Future mein yahan actual SVG Logo aayega */}
            <span className="text-white text-3xl font-bold">ERP</span>
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight text-slate-900">
            Luviio Workspace
          </h1>
          <p className="text-lg text-slate-600">
            Enterprise Resource Planning System. Manage your business efficiently.
          </p>
        </div>

        {/* Call to Action Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
          <Link href="/dashboard" className="w-full sm:w-auto">
            {/* Hamara custom CDUI Button */}
            <Button size="lg" className="w-full shadow-md">
              Enter Dashboard
            </Button>
          </Link>
          
          {/* Auth Route ke liye secondary button */}
          <Link href="/login" className="w-full sm:w-auto">
            <Button variant="outline" size="lg" className="w-full bg-white">
              Admin Login
            </Button>
          </Link>
        </div>

        {/* Footer info */}
        <div className="pt-12 text-sm text-slate-500">
          <p>&copy; {new Date().getFullYear()} Luviio.in. Secure Portal.</p>
        </div>

      </div>
    </div>
 );
}