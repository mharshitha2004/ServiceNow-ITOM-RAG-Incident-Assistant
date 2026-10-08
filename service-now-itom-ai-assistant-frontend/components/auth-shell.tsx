'use client'

import { useState } from 'react'
import type { InputHTMLAttributes, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import Image from 'next/image'
import { Eye, EyeOff } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Split layout: image on one side (large screens), form on the other over a dot grid. */
export function AuthShell({
  children,
  imageSrc,
  imageSide = 'left',
  imagePosition = '75% top',
}: {
  children: ReactNode
  imageSrc: string
  imageSide?: 'left' | 'right'
  imagePosition?: string
}) {
  const right = imageSide === 'right'
  return (
    <div className="grid min-h-[calc(100dvh-4rem)] lg:grid-cols-2">
      <div className={cn('relative hidden lg:block', right && 'lg:order-2')}>
        {/* Stays in view while the form scrolls; starts at the very top so nothing is cut off */}
        <div className="sticky top-0 h-dvh overflow-hidden bg-[#061C24]">
          <Image
            src={imageSrc}
            alt=""
            fill
            priority
            unoptimized
            sizes="50vw"
            className="object-cover"
            style={{ objectPosition: imagePosition }}
          />
          <div
            className={cn(
              'absolute inset-y-0 w-32 from-background to-transparent',
              right ? 'left-0 bg-gradient-to-r' : 'right-0 bg-gradient-to-l',
            )}
            aria-hidden="true"
          />
        </div>
      </div>

      <div className="relative isolate flex items-center justify-center overflow-hidden px-4 py-12 sm:px-6">
        <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
          <div className="absolute left-1/2 top-[-200px] h-[480px] w-[720px] -translate-x-1/2 rounded-full bg-primary/[0.08] blur-[120px]" />
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: 'radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px)',
              backgroundSize: '26px 26px',
              maskImage: 'radial-gradient(ellipse 80% 70% at 50% 40%, #000 25%, transparent 80%)',
              WebkitMaskImage: 'radial-gradient(ellipse 80% 70% at 50% 40%, #000 25%, transparent 80%)',
            }}
          />
        </div>
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  )
}

export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-card/70 p-6 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.6)] backdrop-blur sm:p-8">
      <div className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/[0.08] px-3 py-1 text-xs font-medium text-primary">
        <span className="size-1.5 rounded-full bg-primary" />
        ServiceNow ITOM · AI Assistant
      </div>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
      <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{subtitle}</p>
      {children}
      <p className="mt-6 text-center text-sm text-muted-foreground">{footer}</p>
    </div>
  )
}

type FieldProps = { label: string; icon: LucideIcon; hint?: string } & InputHTMLAttributes<HTMLInputElement>

export function AuthField({ label, icon: Icon, hint, id, type, ...props }: FieldProps) {
  const [show, setShow] = useState(false)
  const isPassword = type === 'password'

  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-foreground">
        {label}
      </label>
      <div className="relative">
        <Icon
          className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          id={id}
          type={isPassword && show ? 'text' : type}
          className={cn(
            'w-full rounded-xl border border-border/70 bg-background/60 py-2.5 pl-10 text-sm outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-primary/50 focus:ring-2 focus:ring-primary/15',
            isPassword ? 'pr-10' : 'pr-3',
          )}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            aria-label={show ? 'Hide password' : 'Show password'}
            className="absolute right-2.5 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:text-foreground"
          >
            {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        )}
      </div>
      {hint && <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}