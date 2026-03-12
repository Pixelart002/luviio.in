/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  
  modularizeImports: {
    'lucide-react': {
      transform: 'lucide-react/dist/esm/icons/{{member}}',
    },
  },
  
  async rewrites() {
    return [
      // 1. Vercel Monorepo Hack (Next.js ko /frontend/ folder ke baare mein sikhana)
      {
        source: '/frontend/:path*',
        destination: '/:path*',
      },
      
      // 🛑 2. THE REAL-WORLD FIX: Proxy SIRF tab chalegi jab tum PC (localhost) pe hoge.
      // Vercel (Production) par yeh code hide ho jayega aur Vercel loop me nahi phasega!
      ...(process.env.NODE_ENV === 'development'
        ? [
            {
              source: '/api/v1/:path*',
              destination: 'http://127.0.0.1:8000/api/v1/:path*',
            },
          ]
        : []),
    ];
  },
  
  webpack: (config, { dev, isServer }) => {
    config.module.rules.push({
      test: /\.svg$/i,
      issuer: /\.[jt]sx?$/,
      use: ['@svgr/webpack'],
    });
    
    return config;
  },
};

module.exports = nextConfig;