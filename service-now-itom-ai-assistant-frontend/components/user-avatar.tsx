'use client'

import { useEffect, useState } from 'react'
import { avatarUrl, type User } from '@/lib/auth'
import { useAuth } from '@/lib/auth-context'
import { cn } from '@/lib/utils'

/**
 * "Mandadi Harshitha Reddy" -> "MR" (first word + last word).
 * "Priya" -> "PR" (first two letters, for a single-word name).
 */
export function getInitials(name: string): string {
  const trimmed = (name || '').trim()

  if (!trimmed) return '?'

  const parts = trimmed.split(/\s+/)

  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  }

  return trimmed.slice(0, 2).toUpperCase()
}

const SIZE_CLASSES = {
  sm: 'size-7 text-[10px]',
  md: 'size-9 text-xs',
  lg: 'size-20 text-xl',
} as const

export function UserAvatar({
  user: userOverride,
  size = 'md',
  className,
}: {
  /** Defaults to the logged-in user from useAuth(). */
  user?: User | null
  size?: keyof typeof SIZE_CLASSES
  className?: string
}) {
  const { user: contextUser, avatarVersion } = useAuth()
  const user = userOverride ?? contextUser

  const [imgFailed, setImgFailed] = useState(false)

  // A removed/replaced photo should get a fresh chance to load rather
  // than staying stuck showing initials from an earlier failed request.
  useEffect(() => {
    setImgFailed(false)
  }, [avatarVersion])

  if (!user) {
    return (
      <span
        className={cn(
          'flex shrink-0 items-center justify-center rounded-full bg-secondary text-foreground',
          SIZE_CLASSES[size],
          className,
        )}
        aria-hidden="true"
      >
        ?
      </span>
    )
  }

  const showPhoto = user.hasAvatar && !imgFailed

  return (
    <span
      className={cn(
        'relative flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-primary to-violet font-semibold text-white',
        SIZE_CLASSES[size],
        className,
      )}
    >
      {showPhoto ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`${avatarUrl()}?v=${avatarVersion}`}
          alt={`${user.name || user.email}'s avatar`}
          className="size-full object-cover"
          onError={() => setImgFailed(true)}
        />
      ) : (
        <span aria-hidden="true">{getInitials(user.name || user.email)}</span>
      )}
    </span>
  )
}