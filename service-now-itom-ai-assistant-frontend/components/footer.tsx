import Link from 'next/link'
import { SiteLogo } from '@/components/site-logo'

const productLinks = [
  { href: '/', label: 'Home' },
  { href: '/documentation', label: 'Documentation Assistant' },
  { href: '/incident', label: 'Incident Assistant' },
]

export function Footer() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <SiteLogo />
          <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
            Answers from the ITOM documentation, and incidents raised in ServiceNow, from one conversation.
          </p>
        </div>

        <nav aria-label="Footer" className="flex flex-col gap-3 md:items-end">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Product</span>
          {productLinks.map((link) => (
            <Link key={link.href} href={link.href} className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              {link.label}
            </Link>
          ))}
        </nav>
      </div>

      <div className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 text-xs text-muted-foreground sm:px-6 md:flex-row md:items-center md:justify-between">
          <p>&copy; {new Date().getFullYear()} ServiceNow ITOM AI Assistant. An independent portfolio project.</p>
          <p>ServiceNow is a trademark of ServiceNow, Inc. Not affiliated with or endorsed by ServiceNow.</p>
        </div>
      </div>
    </footer>
  )
}