import { cn } from '@/lib/utils'

/**
 * Background for the chat pages (soft glow, dot grid, twinkling sparks) plus a
 * reusable <Sparks /> layer for the home page. Put either as the FIRST child of a
 * wrapper that has `relative isolate`.
 */

export type SparkItem = {
  size: number
  color: string
  opacity: number
  delay: string
  dur: string
  top?: string
  /** Distance from the bottom edge in px (used for the padding bands). */
  bottom?: number
  /** Free position, as a % of the width (used on the chat pages). */
  left?: string
  /**
   * Gutter position: the spark sits outside the centred content column, `offset`
   * px away from its edge. On narrow screens there is no gutter, so it is simply
   * clipped, and it can never overlap text or cards.
   */
  side?: 'left' | 'right'
  offset?: number
}

const GREEN = '#59D84A'
const TEAL = '#12BFCB'

/** Chat pages: the chat column is narrow, so sparks live in the outer 15% on each side. */
const EDGE_SPARKS: SparkItem[] = [
  { left: '5%', top: '16%', size: 22, color: GREEN, opacity: 0.55, delay: '0s', dur: '4s' },
  { left: '12%', top: '38%', size: 10, color: TEAL, opacity: 0.5, delay: '1.2s', dur: '3.4s' },
  { left: '8%', top: '64%', size: 16, color: TEAL, opacity: 0.45, delay: '2.1s', dur: '5s' },
  { left: '3%', top: '86%', size: 9, color: GREEN, opacity: 0.45, delay: '0.6s', dur: '3.8s' },
  { left: '93%', top: '12%', size: 12, color: TEAL, opacity: 0.5, delay: '0.9s', dur: '3.6s' },
  { left: '88%', top: '34%', size: 24, color: GREEN, opacity: 0.5, delay: '1.8s', dur: '4.6s' },
  { left: '95%', top: '60%', size: 10, color: GREEN, opacity: 0.45, delay: '0.3s', dur: '3.2s' },
  { left: '86%', top: '82%', size: 18, color: TEAL, opacity: 0.45, delay: '2.6s', dur: '5.2s' },
]

/** Home page sections: only in the empty space beside the content column. */
export const GUTTER_SPARKS: SparkItem[] = [
  { side: 'left', offset: 30, top: '12%', size: 18, color: GREEN, opacity: 0.55, delay: '0s', dur: '4s' },
  { side: 'left', offset: 95, top: '32%', size: 10, color: TEAL, opacity: 0.5, delay: '1.2s', dur: '3.4s' },
  { side: 'left', offset: 20, top: '56%', size: 22, color: TEAL, opacity: 0.45, delay: '2.1s', dur: '5s' },
  { side: 'left', offset: 110, top: '76%', size: 12, color: GREEN, opacity: 0.5, delay: '0.6s', dur: '3.8s' },
  { side: 'left', offset: 50, top: '91%', size: 9, color: GREEN, opacity: 0.4, delay: '1.7s', dur: '4.2s' },
  { side: 'right', offset: 40, top: '8%', size: 12, color: TEAL, opacity: 0.5, delay: '0.9s', dur: '3.6s' },
  { side: 'right', offset: 100, top: '28%', size: 22, color: GREEN, opacity: 0.5, delay: '1.8s', dur: '4.6s' },
  { side: 'right', offset: 30, top: '52%', size: 10, color: GREEN, opacity: 0.45, delay: '0.3s', dur: '3.2s' },
  { side: 'right', offset: 120, top: '72%', size: 18, color: TEAL, opacity: 0.45, delay: '2.6s', dur: '5.2s' },
  { side: 'right', offset: 60, top: '90%', size: 9, color: TEAL, opacity: 0.4, delay: '0.4s', dur: '4.4s' },
]

/** Hero: same idea, different spots so it doesn't look copied. */
export const HERO_SPARKS: SparkItem[] = [
  { side: 'left', offset: 25, top: '10%', size: 20, color: GREEN, opacity: 0.55, delay: '0s', dur: '4s' },
  { side: 'left', offset: 85, top: '38%', size: 12, color: TEAL, opacity: 0.5, delay: '1.4s', dur: '3.6s' },
  { side: 'left', offset: 35, top: '68%', size: 16, color: TEAL, opacity: 0.45, delay: '2.2s', dur: '4.8s' },
  { side: 'left', offset: 100, top: '88%', size: 9, color: GREEN, opacity: 0.4, delay: '0.7s', dur: '3.9s' },
  { side: 'right', offset: 30, top: '12%', size: 14, color: TEAL, opacity: 0.5, delay: '0.8s', dur: '3.7s' },
  { side: 'right', offset: 90, top: '34%', size: 24, color: GREEN, opacity: 0.5, delay: '1.9s', dur: '5s' },
  { side: 'right', offset: 40, top: '62%', size: 12, color: GREEN, opacity: 0.45, delay: '0.3s', dur: '3.3s' },
  { side: 'right', offset: 110, top: '86%', size: 16, color: TEAL, opacity: 0.45, delay: '2.7s', dur: '4.9s' },
]

/**
 * Sparks that sit inside the empty top/bottom padding of a section, at any screen
 * width. Sections have 80px+ of vertical padding, so these stay clear of all text.
 */
const BAND_SPARKS: SparkItem[] = [
  { left: '4%', top: '30px', size: 14, color: GREEN, opacity: 0.55, delay: '0s', dur: '4s' },
  { left: '17%', top: '18px', size: 9, color: TEAL, opacity: 0.5, delay: '1.1s', dur: '3.4s' },
  { left: '33%', top: '40px', size: 12, color: GREEN, opacity: 0.5, delay: '2s', dur: '4.6s' },
  { left: '52%', top: '20px', size: 18, color: TEAL, opacity: 0.5, delay: '0.5s', dur: '5s' },
  { left: '68%', top: '42px', size: 9, color: GREEN, opacity: 0.45, delay: '1.6s', dur: '3.6s' },
  { left: '81%', top: '22px', size: 14, color: TEAL, opacity: 0.5, delay: '2.4s', dur: '4.2s' },
  { left: '94%', top: '38px', size: 20, color: GREEN, opacity: 0.55, delay: '0.8s', dur: '4.8s' },
  { left: '9%', bottom: 26, size: 18, color: TEAL, opacity: 0.5, delay: '1.3s', dur: '4.4s' },
  { left: '24%', bottom: 44, size: 9, color: GREEN, opacity: 0.45, delay: '0.2s', dur: '3.3s' },
  { left: '43%', bottom: 20, size: 12, color: GREEN, opacity: 0.5, delay: '2.2s', dur: '4.9s' },
  { left: '60%', bottom: 38, size: 16, color: TEAL, opacity: 0.5, delay: '0.9s', dur: '3.9s' },
  { left: '74%', bottom: 18, size: 9, color: GREEN, opacity: 0.45, delay: '1.9s', dur: '3.5s' },
  { left: '90%', bottom: 32, size: 14, color: TEAL, opacity: 0.5, delay: '0.6s', dur: '4.5s' },
]

/** Home sections: side gutters (wide screens) + top/bottom padding bands (all screens). */
export const SECTION_SPARKS: SparkItem[] = [...GUTTER_SPARKS, ...BAND_SPARKS]

/** Hero: tiny ones above the chat preview and a row along the bottom padding. */
export const HERO_BAND: SparkItem[] = [
  { left: '40%', top: '5px', size: 9, color: TEAL, opacity: 0.5, delay: '0.4s', dur: '3.4s' },
  { left: '63%', top: '4px', size: 10, color: GREEN, opacity: 0.5, delay: '1.5s', dur: '4s' },
  { left: '88%', top: '6px', size: 9, color: TEAL, opacity: 0.45, delay: '2.3s', dur: '3.7s' },
  { left: '6%', bottom: 24, size: 16, color: GREEN, opacity: 0.5, delay: '0.9s', dur: '4.3s' },
  { left: '21%', bottom: 42, size: 9, color: TEAL, opacity: 0.45, delay: '2s', dur: '3.5s' },
  { left: '38%', bottom: 20, size: 12, color: GREEN, opacity: 0.5, delay: '0.2s', dur: '4.7s' },
  { left: '57%', bottom: 40, size: 18, color: TEAL, opacity: 0.5, delay: '1.4s', dur: '5s' },
  { left: '76%', bottom: 22, size: 9, color: GREEN, opacity: 0.45, delay: '2.6s', dur: '3.6s' },
  { left: '92%', bottom: 38, size: 14, color: TEAL, opacity: 0.5, delay: '0.7s', dur: '4.1s' },
]

// Half of the content column (max-w-6xl = 1152px) plus a little breathing room.
const CONTENT_HALF = 576 + 16

function positionFor(s: SparkItem): React.CSSProperties {
  // max-w-6xl = 72rem, so half = 36rem, plus 1rem breathing room
  if (s.side === 'left') {
    return { left: `calc(50% - 37rem - ${(s.offset ?? 0) + s.size}px)`, top: s.top, bottom: s.bottom }
  }
  if (s.side === 'right') {
    return { left: `calc(50% + 37rem + ${s.offset ?? 0}px)`, top: s.top, bottom: s.bottom }
  }
  return { left: s.left, top: s.top, bottom: s.bottom }
}

function Spark({ item }: { item: SparkItem }) {
  const { size, color, opacity, delay, dur } = item
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={cn('absolute animate-pulse motion-reduce:animate-none')}
      style={{
        color,
        opacity,
        filter: `drop-shadow(0 0 ${size / 2}px ${color})`,
        animationDelay: delay,
        animationDuration: dur,
        ...positionFor(item),
      }}
      aria-hidden="true"
    >
      <path
        d="M12 1.5C13.3 8.6 15.4 10.7 22.5 12 15.4 13.3 13.3 15.4 12 22.5 10.7 15.4 8.6 13.3 1.5 12 8.6 10.7 10.7 8.6 12 1.5Z"
        fill="currentColor"
      />
    </svg>
  )
}

/** A spark that sits in the normal text flow (next to a badge or headline), so it can never overlap words. */
export function InlineSpark({
  size = 20,
  color = GREEN,
  delay = '0s',
  dur = '4s',
  className,
}: {
  size?: number
  color?: string
  delay?: string
  dur?: string
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={cn('shrink-0 animate-pulse motion-reduce:animate-none', className)}
      style={{
        color,
        filter: `drop-shadow(0 0 ${size / 2.5}px ${color})`,
        animationDelay: delay,
        animationDuration: dur,
      }}
      aria-hidden="true"
    >
      <path
        d="M12 1.5C13.3 8.6 15.4 10.7 22.5 12 15.4 13.3 13.3 15.4 12 22.5 10.7 15.4 8.6 13.3 1.5 12 8.6 10.7 10.7 8.6 12 1.5Z"
        fill="currentColor"
      />
    </svg>
  )
}

/** A small group of three sparks for the empty right side of a section heading (large screens only). */
export function SparkCluster({ className }: { className?: string }) {
  return (
    <div className={cn('pointer-events-none relative hidden h-36 w-44 lg:block', className)} aria-hidden="true">
      <InlineSpark size={42} color={GREEN} className="absolute right-10 top-3" />
      <InlineSpark size={18} color={TEAL} delay="1.2s" dur="3.4s" className="absolute right-1 top-16" />
      <InlineSpark size={12} color={GREEN} delay="2s" dur="4.6s" className="absolute right-28 top-24" />
    </div>
  )
}

/** Twinkling four-point sparks. Place inside a wrapper that has `relative isolate`. */
export function Sparks({ items = EDGE_SPARKS }: { items?: SparkItem[] }) {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
      {items.map((s, i) => (
        <Spark key={i} item={s} />
      ))}
    </div>
  )
}

export function ChatBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div className="absolute left-1/2 top-[-220px] h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-primary/[0.07] blur-[130px]" />
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: 'radial-gradient(rgba(255,255,255,0.09) 1px, transparent 1px)',
          backgroundSize: '26px 26px',
          maskImage: 'radial-gradient(ellipse 85% 75% at 50% 35%, #000 30%, transparent 85%)',
          WebkitMaskImage: 'radial-gradient(ellipse 85% 75% at 50% 35%, #000 30%, transparent 85%)',
        }}
      />
      <Sparks />
    </div>
  )
}