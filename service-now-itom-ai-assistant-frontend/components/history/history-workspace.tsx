'use client'

import type { ReactNode } from 'react'
import {
  HistorySidebar,
  type HistorySidebarProps,
} from '@/components/history/history-sidebar'

/**
 * Page layout for the assistants: history sidebar on the left, the chat
 * on the right. The chat keeps its own full-height layout inside.
 */
export function HistoryWorkspace({
  children,
  ...sidebarProps
}: HistorySidebarProps & { children: ReactNode }) {
  return (
    <div className="relative flex h-[calc(100dvh-4rem)] overflow-hidden">
      <HistorySidebar {...sidebarProps} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}