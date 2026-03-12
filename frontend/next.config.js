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
      // 🚀 THE MAGIC FIX: Vercel ke '/frontend/' path ko Next.js se chupana
      // (Iske bina Next.js 404 error dega kyunki uske paas frontend naam ka folder nahi hai)
      {
        source: '/frontend/:path*',
        destination: '/:path*',
      },
      
      // 🔌 Local Dev & Proxy: 
      // Vercel pe backend vercel.json handle karega, par Local PC pe ye proxy FastAPI (8000) ko call karegi
      {
        source: '/api/v1/:path*',
        destination: process.env.NEXT_PUBLIC_API_URL ?
          `${process.env.NEXT_PUBLIC_API_URL}/api/v1/:path*` :
          'http://127.0.0.1:8000/api/v1/:path*',
      },
    ];
  },
  
  // Webpack specific customizations
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