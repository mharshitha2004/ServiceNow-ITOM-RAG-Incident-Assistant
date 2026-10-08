'use client'

import { useCallback, useEffect, useState } from 'react'
import type { ClipboardEvent } from 'react'

/**
 * Shared image-attachment state for chat composers.
 *
 * Handles picking a file, pasting a screenshot / copied image straight
 * from the clipboard, validating it, and giving you a preview URL.
 * Used by both the Incident Assistant and the Documentation Assistant.
 */

export const ACCEPTED_IMAGE_TYPES = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
]

const MAX_IMAGE_BYTES = 10 * 1024 * 1024 // 10 MB

export function useImageAttachment() {
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Build (and clean up) the object URL used for the composer preview.
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }

    const url = URL.createObjectURL(file)
    setPreviewUrl(url)

    return () => URL.revokeObjectURL(url)
  }, [file])

  const attach = useCallback((candidate: File | null | undefined) => {
    if (!candidate) return

    if (!ACCEPTED_IMAGE_TYPES.includes(candidate.type)) {
      setError('Only PNG, JPEG, WebP or GIF images can be attached.')
      return
    }

    if (candidate.size > MAX_IMAGE_BYTES) {
      setError('That image is larger than 10 MB.')
      return
    }

    setError(null)
    setFile(candidate)
  }, [])

  const clear = useCallback(() => {
    setFile(null)
    setError(null)
  }, [])

  // Attach to a textarea's onPaste. Screenshots and images copied from a
  // web page arrive on the clipboard as files, not text.
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

      // Only swallow the paste if there's no text alongside the image,
      // so copying text + image together still pastes the text.
      if (!e.clipboardData.getData('text/plain')) {
        e.preventDefault()
      }
    },
    [attach],
  )

  return { file, previewUrl, error, attach, clear, handlePaste }
}