/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true, 
  
  modularizeImports: {
    'lucide-react': {
      transform: 'lucide-react/dist/esm/icons/{{member}}',
    },
  },

  // 🚀 Magic Proxy for FastAPI Integration
  async rewrites() {
    return [
      {
        // Source: Frontend mein hum hamesha '/api/v1/...' call karenge
        source: '/api/v1/:path*',
        
        // Destination: Agar Vercel pe hain toh Backend URL pe bhejo, warna Localhost (8000) pe bhejo
        destination: process.env.NEXT_PUBLIC_API_URL 
          ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1/:path*` 
          : 'http://127.0.0.1:8000/api/v1/:path*', 
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