/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // SWC compiler use karega for faster builds (Webpack ke upar Next.js ka optimization)
  swcMinify: true, 
  
  // CDUI aur modularity ke liye: Imports ko optimize karta hai taaki bundle size chota rahe
  modularizeImports: {
    'lucide-react': {
      transform: 'lucide-react/dist/esm/icons/{{member}}',
    },
  },

  // 🚀 Magic Proxy for FastAPI Integration
  async rewrites() {
    return [
      {
        // Frontend mein hum '/api/backend/...' call karenge
        source: '/api/backend/:path*',
        // Aur wo background mein FastAPI port par forward ho jayega
        destination: process.env.NEXT_PUBLIC_API_URL 
          ? `${process.env.NEXT_PUBLIC_API_URL}/:path*` 
          : 'http://127.0.0.1:8000/api/v1/:path*', 
      },
    ];
  },

  // Webpack specific customizations
  webpack: (config, { dev, isServer }) => {
    // Agar future mein SVG icons ko as React components import karna ho
    config.module.rules.push({
      test: /\.svg$/i,
      issuer: /\.[jt]sx?$/,
      use: ['@svgr/webpack'],
    });

    return config;
  },
};

module.exports = nextConfig;