'use client'

import { useCallback, useEffect, useState } from 'react'
import type { ClipboardEvent } from 'react'

/**
 * Attachment state for the Incident Assistant's composer.
 *
 * A superset of useImageAttachment (still used by the Documentation
 * Assistant, unchanged): this one also accepts .txt log files and .zip
 * archives, since the incident flow can analyze a log file as text or
 * attach an archive to the ServiceNow incident directly, not just
 * screenshots. Kept as a separate hook rather than widening the shared
 * one, so the Documentation Assistant's image-only behavior can't
 * accidentally change.
 */

export type IncidentAttachmentKind = 'image' | 'text' | 'archive'

const ACCEPTED_IMAGE_TYPES = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
]

const ACCEPTED_TEXT_TYPES = ['text/plain']
const ACCEPTED_ARCHIVE_TYPES = ['application/zip', 'application/x-zip-compressed']

const MAX_IMAGE_BYTES = 10 * 1024 * 1024 // 10 MB
const MAX_OTHER_BYTES = 20 * 1024 * 1024 // 20 MB - logs/archives run larger

/** The file picker's accept attribute - images plus .txt/.zip by
 * extension (some browsers report a generic/empty MIME type for
 * these, so the extension is listed explicitly too). */
export const INCIDENT_ATTACHMENT_ACCEPT =
  [...ACCEPTED_IMAGE_TYPES, ...ACCEPTED_TEXT_TYPES, ...ACCEPTED_ARCHIVE_TYPES].join(
    ',',
  ) + ',.txt,.zip'

function detectKind(candidate: File): IncidentAttachmentKind | null {
  const type = candidate.type.toLowerCase()
  const name = candidate.name.toLowerCase()

  if (ACCEPTED_IMAGE_TYPES.includes(type)) return 'image'
  if (ACCEPTED_TEXT_TYPES.includes(type) || name.endsWith('.txt')) return 'text'
  if (ACCEPTED_ARCHIVE_TYPES.includes(type) || name.endsWith('.zip')) return 'archive'

  return null
}

export function useIncidentAttachment() {
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState<IncidentAttachmentKind | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Only an image gets an object URL preview - a .txt/.zip is shown as
  // a plain filename chip instead (see IncidentAttachmentPreview).
  useEffect(() => {
    if (!file || kind !== 'image') {
      setPreviewUrl(null)
      return
    }

    const url = URL.createObjectURL(file)
    setPreviewUrl(url)

    return () => URL.revokeObjectURL(url)
  }, [file, kind])

  const attach = useCallback((candidate: File | null | undefined) => {
    if (!candidate) return

    const detected = detectKind(candidate)

    if (!detected) {
      setError(
        'Only PNG, JPEG, WebP, GIF images, .txt log files, or .zip archives can be attached.',
      )
      return
    }

    const maxBytes = detected === 'image' ? MAX_IMAGE_BYTES : MAX_OTHER_BYTES

    if (candidate.size > maxBytes) {
      setError(`That file is larger than ${maxBytes / (1024 * 1024)} MB.`)
      return
    }

    setError(null)
    setKind(detected)
    setFile(candidate)
  }, [])

  const clear = useCallback(() => {
    setFile(null)
    setKind(null)
    setError(null)
  }, [])

  // Attach to a textarea's onPaste - screenshots copied from elsewhere
  // arrive on the clipboard as files, not text. (Pasting only applies
  // to images; .txt/.zip files are always picked via the file button.)
  const handlePaste = useCallback(
    (e: ClipboardEvent<HTMLElement>) => {
      const items = Array.from(e.clipboardData?.items ?? [])
      const imageItem = items.find(
        (item) => item.kind === 'file' && item.type.startsWith('image/'),
      )

      if (!imageItem) return

      const pasted = imageItem.getAsFile()
      if (!pasted) return

      attach(pasted)

      if (!e.clipboardData.getData('text/plain')) {
        e.preventDefault()
      }
    },
    [attach],
  )

  return { file, kind, previewUrl, error, attach, clear, handlePaste }
}