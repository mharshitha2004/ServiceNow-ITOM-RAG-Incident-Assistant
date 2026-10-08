import { FileArchive, FileText, X } from 'lucide-react'
import type { IncidentAttachmentKind } from '@/lib/use-incident-attachment'

/**
 * Composer preview for a pending incident attachment. An image gets the
 * same thumbnail treatment as ImageAttachmentPreview; a .txt/.zip gets a
 * filename chip instead, since there's nothing to show a thumbnail of.
 */
export function IncidentAttachmentPreview({
  kind,
  src,
  name,
  onRemove,
}: {
  kind: IncidentAttachmentKind
  /** Object URL - only present (and only used) when kind === 'image'. */
  src?: string | null
  name?: string
  onRemove: () => void
}) {
  if (kind === 'image' && src) {
    return (
      <div className="mb-3 flex">
        <div className="relative">
          {/* Blob URL from the browser, so next/image can't optimize it. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={name ? `Attached image: ${name}` : 'Attached image'}
            className="h-24 w-24 rounded-xl border border-border/70 object-cover"
          />
          <button
            type="button"
            onClick={onRemove}
            aria-label="Remove attached image"
            className="absolute -right-2 -top-2 flex size-6 items-center justify-center rounded-full border border-border bg-background text-foreground shadow-md transition-colors hover:bg-secondary"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </div>
    )
  }

  const Icon = kind === 'archive' ? FileArchive : FileText

  return (
    <div className="mb-3 flex">
      <div className="flex items-center gap-2 rounded-xl border border-border/70 bg-secondary/40 py-2 pl-3 pr-2">
        <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="max-w-[16rem] truncate text-sm text-foreground">
          {name || 'Attached file'}
        </span>
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove attached file"
          className="flex size-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  )
}