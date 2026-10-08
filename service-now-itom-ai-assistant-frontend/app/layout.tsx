import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import Script from 'next/script'
import { AuthProvider } from '@/lib/auth-context'
import { ThemeProvider, THEME_NO_FLASH_SCRIPT } from '@/lib/theme-context'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'ServiceNow ITOM AI Assistant',
  description:
    'An AI-powered product documentation and troubleshooting assistant. Ask questions against your product docs and prepare incidents faster.',
  generator: 'v0.app',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  // Themes now toggle at runtime (see lib/theme-context.tsx), so this is
  // just the default browser-chrome hint before the no-flash script runs.
  colorScheme: 'dark',
  themeColor: '#0b1020',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    // No "dark" class here anymore - the inline script below sets it
    // (or leaves it off, for light mode) before the page paints, based
    // on the stored preference. See lib/theme-context.tsx.
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="antialiased font-sans" suppressHydrationWarning>
        {/* next/script with beforeInteractive runs before hydration/paint,
            same as a raw <script> in <head> would, but through Next's own
            mechanism - a bare <script> tag triggers a runtime warning in
            this Next.js/React version. */}
        <Script id="theme-no-flash" strategy="beforeInteractive">
          {THEME_NO_FLASH_SCRIPT}
        </Script>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}