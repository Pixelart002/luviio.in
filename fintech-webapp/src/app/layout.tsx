import type { Metadata } from 'next'
import '../styles/globals.css'

export const metadata: Metadata = {
  title: 'FinSecure | Modern Fintech',
  description: 'Production-ready secure fintech application',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen flex flex-col font-sans">
        {children}
      </body>
    </html>
  )
}