import type { Config } from 'tailwindcss'

const config: Config = {
 // Mobile par performance ke liye sirf unhi files ko scan karo jahan classes use hongi
 content: [
  './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
  './src/components/**/*.{js,ts,jsx,tsx,mdx}',
  './src/app/**/*.{js,ts,jsx,tsx,mdx}',
 ],
 theme: {
  extend: {
   colors: {
    // ERP specific color palette
    brand: {
     50: '#f0f9ff',
     500: '#0ea5e9', // Primary Brand Color
     900: '#0c4a6e',
    },
    surface: {
     light: '#ffffff',
     dark: '#0f172a',
     muted: '#f1f5f9', // Backgrounds for tables/cards
    },
    status: {
     success: '#10b981', // For approved invoices, etc.
     warning: '#f59e0b', // Pending items
     danger: '#ef4444', // Errors, deletes
    }
   },
   fontFamily: {
    sans: ['var(--font-inter)'], // Clean font for data readability
   },
  },
 },
 plugins: [
  // Future mein forms styling ke liye Tailwind forms plugin add kar sakte ho
 ],
}
export default config