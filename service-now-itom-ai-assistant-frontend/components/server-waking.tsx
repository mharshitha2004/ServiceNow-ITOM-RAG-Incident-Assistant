'use client'

import { Loader2 } from 'lucide-react'
import { ChatBackdrop } from '@/components/chat-backdrop'

/**
 * Shown while the backend is waking up. The API runs on Render's free
 * tier, which puts the server to sleep after ~15 minutes without
 * traffic; the first request after that takes 30-60 seconds while it
 * boots. Without this, pages that wait for the login check just render
 * nothing for that whole time.
 */
export function ServerWaking({ fullPage = true }: { fullPage?: boolean }) {
  const card = (
    <div
      role="status"
      aria-live="polite"
      className="mx-auto w-full max-w-sm rounded-2xl border border-border/70 bg-card/60 p-6 text-center"
    >
      <Loader2 className="mx-auto size-6 animate-spin text-primary" />
      <h2 className="mt-4 text-base font-semibold text-foreground">
        Waking up the server…
      </h2>
      <p className="mt-1.5 text-sm text-muted-foreground">
        The backend runs on free hosting that sleeps when nobody has used it
        for a while. The first load can take up to a minute. After that,
        everything is fast.
      </p>
    </div>
  )

  if (!fullPage) return card

  return (
    <div className="relative isolate flex h-[calc(100dvh-4rem)] items-center justify-center px-4">
      <ChatBackdrop />
      {card}
    </div>
  )
}

/** Small corner notice for pages that don't block on the login check. */
export function ServerWakingToast() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 left-1/2 z-50 flex max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-2 rounded-full border border-border/70 bg-card/95 px-4 py-2 text-sm text-muted-foreground shadow-lg backdrop-blur"
    >
      <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
      Waking up the server, this can take up to a minute…
    </div>
  )
}
