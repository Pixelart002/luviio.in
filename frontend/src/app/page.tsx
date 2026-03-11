// src/app/page.tsx
import { Button } from '@/components/ui/Button';

export default function StoreFront() {
  return (
    // 🧹 Outer wrapper se min-h-screen hata diya kyunki ab wo layout.tsx handle kar raha hai
    <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
      
      {/* 🛍️ Sirf Hero Section Bacha Hai */}
      <div className="max-w-3xl space-y-8 mt-12 md:mt-20">
        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-slate-900">
          Elevate Your Everyday <br/>
          <span className="text-brand-500 text-4xl md:text-6xl">Premium Collection</span>
        </h1>
        
        <p className="text-lg md:text-xl leading-relaxed text-slate-600 max-w-2xl mx-auto">
          Discover our latest arrivals. Designed for comfort, engineered for style. Upgrade your wardrobe with Luviio.
        </p>
        
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
          <Button size="lg" variant="primary" className="w-full sm:w-auto px-8">
            Shop Now
          </Button>
          <Button size="lg" variant="outline" className="w-full sm:w-auto px-8">
            View Categories
          </Button>
        </div>
      </div>

    </div>
  );
}