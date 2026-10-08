import { X } from 'lucide-react'

/**
 * Thumbnail of an image that is attached but not sent yet, with a
 * remove button - the same pattern Claude / ChatGPT use above the
 * message box.
 */
export function ImageAttachmentPreview({
  src,
  name,
  onRemove,
}: {
  src: string
  name?: string
  onRemove: () => void
}) {
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