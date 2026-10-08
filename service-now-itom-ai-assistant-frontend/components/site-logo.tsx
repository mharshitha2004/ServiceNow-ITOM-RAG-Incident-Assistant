import Link from 'next/link'
import { cn } from '@/lib/utils'

/**
 * Logo mark: a large green-to-teal four-point spark (the AI assistant) with two
 * smaller sparks, on a dark teal tile. Inline SVG so it stays crisp at any size
 * and needs no image file.
 */
function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" fill="none" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="itom-mark-bg" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0F4A52" />
          <stop offset="1" stopColor="#06222A" />
        </linearGradient>
        <linearGradient id="itom-mark-spark" x1="7" y1="10" x2="34" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#59D84A" />
          <stop offset="1" stopColor="#12BFCB" />
        </linearGradient>
      </defs>

      <rect width="40" height="40" rx="11" fill="url(#itom-mark-bg)" />
      <rect x="0.5" y="0.5" width="39" height="39" rx="10.5" stroke="#59D84A" strokeOpacity="0.3" />

      {/* Main spark */}
      <path
        d="M20 7C21.8 15.2 24.8 18.2 33 20 24.8 21.8 21.8 24.8 20 33 18.2 24.8 15.2 21.8 7 20 15.2 18.2 18.2 15.2 20 7Z"
        fill="url(#itom-mark-spark)"
      />
      {/* Small sparks */}
      <path
        d="M31 4.5C31.4 7.2 32.8 8.6 35.5 9 32.8 9.4 31.4 10.8 31 13.5 30.6 10.8 29.2 9.4 26.5 9 29.2 8.6 30.6 7.2 31 4.5Z"
        fill="#7DE39A"
      />
      <path
        d="M9.5 28C9.8 29.9 10.6 30.7 12.5 31 10.6 31.3 9.8 32.1 9.5 34 9.2 32.1 8.4 31.3 6.5 31 8.4 30.7 9.2 29.9 9.5 28Z"
        fill="#12BFCB"
      />
    </svg>
  )
}

export function SiteLogo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        'group flex items-center gap-3.5 rounded-xl outline-none',
        'focus-visible:ring-2 focus-visible:ring-primary/50',
        className,
      )}
    >
      <LogoMark className="size-12 shrink-0 transition-transform duration-300 group-hover:scale-[1.04]" />

      <span className="flex flex-col justify-center font-[family-name:var(--font-jakarta)]">
        <span className="text-[16px] font-bold leading-[1.1] tracking-[-0.02em] text-foreground">
          ServiceNow ITOM
        </span>
        <span className="mt-1 text-sm font-small leading-none text-muted-foreground">
          AI Assistant
        </span>
      </span>
    </Link>
  )
}