'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  Plus,
  Trash2,
} from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import {
  deleteConversation,
  listConversations,
  type ConversationKind,
  type ConversationSummary,
} from '@/lib/history'
import { cn } from '@/lib/utils'

const STORAGE_KEY = 'itom-history-open'

export type HistorySidebarProps = {
  kind: ConversationKind
  /** The conversation currently open in the chat, if any. */
  activeId: string | null
  /** Change this number to make the list reload (e.g. after a message is saved). */
  refreshKey: number
  onSelect: (id: string) => void
  onNewChat: () => void
  /** Called after a conversation is deleted, so the chat can reset if it was open. */
  onDeleted?: (id: string) => void
}

function startOfDay(date: Date): number {
  return new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  ).getTime()
}

function groupLabel(iso: string, now: Date): string {
  const days = Math.round(
    (startOfDay(now) - startOfDay(new Date(iso))) / 86_400_000,
  )

  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days <= 7) return 'Previous 7 days'
  return 'Older'
}

function groupConversations(items: ConversationSummary[]) {
  const now = new Date()
  const groups: { label: string; items: ConversationSummary[] }[] = []

  for (const item of items) {
    const label = groupLabel(item.updatedAt, now)
    const last = groups[groups.length - 1]

    if (last && last.label === label) {
      last.items.push(item)
    } else {
      groups.push({ label, items: [item] })
    }
  }

  return groups
}

export function HistorySidebar({
  kind,
  activeId,
  refreshKey,
  onSelect,
  onNewChat,
  onDeleted,
}: HistorySidebarProps) {
  const { user, isLoading: authLoading } = useAuth()

  const [open, setOpen] = useState(true)
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Restore the person's last choice. On phones the sidebar covers the chat,
  // so it always starts closed there.
  useEffect(() => {
    const isDesktop = window.matchMedia('(min-width: 768px)').matches
    const stored = window.localStorage.getItem(STORAGE_KEY)

    setOpen(isDesktop ? stored !== '0' : false)
  }, [])

  function setOpenAndRemember(next: boolean) {
    setOpen(next)
    window.localStorage.setItem(STORAGE_KEY, next ? '1' : '0')
  }

  useEffect(() => {
    if (!user) {
      setItems([])
      return
    }

    let cancelled = false

    setLoading(true)
    setError(null)

    listConversations(kind)
      .then((result) => {
        if (!cancelled) setItems(result)
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load your history.")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [kind, user, refreshKey])

  async function handleDelete(item: ConversationSummary) {
    if (!window.confirm('Delete this conversation? This cannot be undone.')) {
      return
    }

    try {
      await deleteConversation(item.id)
      setItems((prev) => prev.filter((i) => i.id !== item.id))
      onDeleted?.(item.id)
    } catch {
      setError("Couldn't delete that conversation.")
    }
  }

  function handleSelect(id: string) {
    onSelect(id)

    // On phones, get out of the way once something is picked.
    if (!window.matchMedia('(min-width: 768px)').matches) {
      setOpen(false)
    }
  }

  const groups = useMemo(() => groupConversations(items), [items])

  return (
    <>
      {/* Phones: tap outside to close */}
      {open && (
        <button
          type="button"
          aria-label="Close history"
          onClick={() => setOpenAndRemember(false)}
          className="absolute inset-0 z-20 bg-black/50 md:hidden"
        />
      )}

      {/* Show-history arrow, only while the sidebar is hidden */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpenAndRemember(true)}
          aria-label="Show history"
          aria-expanded={false}
          title="Show history"
          className="absolute left-2 top-3 z-10 flex size-8 items-center justify-center rounded-lg border border-border/70 bg-card/80 text-muted-foreground backdrop-blur transition-colors hover:border-primary/40 hover:text-foreground"
        >
          <ChevronRight className="size-4" />
        </button>
      )}

      <aside
        aria-label="Conversation history"
        inert={!open}
        className={cn(
          'z-30 flex flex-col overflow-hidden border-r border-border/70 bg-background transition-all duration-300',
          'max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:w-72',
          open
            ? 'md:w-72'
            : 'border-r-0 max-md:-translate-x-full md:w-0',
        )}
      >
        {/* Fixed inner width so text doesn't reflow while the panel animates */}
        <div className="flex h-full w-72 shrink-0 flex-col">
          <div className="flex items-center justify-between px-4 pb-2 pt-4">
            <h2 className="text-sm font-semibold text-foreground">History</h2>
            <button
              type="button"
              onClick={() => setOpenAndRemember(false)}
              aria-label="Hide history"
              aria-expanded={open}
              title="Hide history"
              className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <ChevronLeft className="size-4" />
            </button>
          </div>

          <div className="px-3 pb-3">
            <button
              type="button"
              onClick={() => {
                onNewChat()
                if (!window.matchMedia('(min-width: 768px)').matches) {
                  setOpen(false)
                }
              }}
              className="flex w-full items-center gap-2 rounded-xl border border-primary/30 bg-primary/10 px-3 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
            >
              <Plus className="size-4" aria-hidden="true" />
              New chat
            </button>
          </div>

          <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
            {authLoading ? null : !user ? (
              <div className="rounded-xl border border-border/70 bg-secondary/40 p-4 text-sm text-muted-foreground">
                <p>Log in to save your chats and come back to them later.</p>
                <Link
                  href="/login"
                  className="mt-3 inline-block font-medium text-primary hover:underline"
                >
                  Log in
                </Link>
              </div>
            ) : error ? (
              <p className="px-1 text-sm text-red-400">{error}</p>
            ) : loading && items.length === 0 ? (
              <ul className="space-y-2" aria-hidden="true">
                {[0, 1, 2, 3].map((i) => (
                  <li
                    key={i}
                    className="h-9 animate-pulse rounded-lg bg-secondary/60"
                  />
                ))}
              </ul>
            ) : items.length === 0 ? (
              <p className="px-1 text-sm text-muted-foreground">
                No conversations yet. Ask something and it will show up here.
              </p>
            ) : (
              <div className="space-y-5">
                {groups.map((group) => (
                  <div key={group.label}>
                    <p className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {group.label}
                    </p>
                    <ul className="space-y-0.5">
                      {group.items.map((item) => {
                        const active = item.id === activeId

                        return (
                          <li key={item.id} className="group relative">
                            <button
                              type="button"
                              onClick={() => handleSelect(item.id)}
                              aria-current={active ? 'true' : undefined}
                              className={cn(
                                'flex w-full items-center gap-2 rounded-lg px-3 py-2 pr-9 text-left text-sm transition-colors',
                                active
                                  ? 'bg-white text-black shadow-sm ring-1 ring-black/10 dark:bg-card dark:text-white dark:shadow-none dark:ring-white/15'
                                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
                              )}
                            >
                              <MessageSquare
                                className="size-3.5 shrink-0 opacity-60"
                                aria-hidden="true"
                              />
                              <span className="truncate">{item.title}</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => void handleDelete(item)}
                              aria-label={`Delete conversation: ${item.title}`}
                              className={cn(
                                'absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground transition hover:bg-secondary hover:text-red-400 focus-visible:opacity-100 group-hover:opacity-100',
                                active ? 'opacity-100' : 'opacity-0',
                              )}
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </nav>
        </div>
      </aside>
    </>
  )
}