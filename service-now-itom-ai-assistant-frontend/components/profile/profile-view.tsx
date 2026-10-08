'use client'

import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import Link from 'next/link'
import {
  Lock,
  LogIn,
  Mail,
  Trash2,
  Upload,
  UserRound,
} from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import {
  changePassword,
  removeAvatar,
  updateProfile,
  uploadAvatar,
} from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { AuthField } from '@/components/auth-shell'
import { UserAvatar } from '@/components/user-avatar'
import { ServerWaking } from '@/components/server-waking'

function SectionCard({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-card/70 p-6 shadow-[0_20px_60px_-30px_rgba(0,0,0,0.5)] sm:p-8">
      <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      {children}
    </div>
  )
}

function LoginRequired() {
  return (
    <div className="flex items-center justify-center px-4 py-24">
      <div className="w-full max-w-sm rounded-2xl border border-border/70 bg-card/60 p-6 text-center">
        <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-primary/10">
          <LogIn className="size-4 text-primary" />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-foreground">
          Log in to view your profile
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Your profile is tied to your account, so you'll need to log in
          first.
        </p>
        <div className="mt-5 flex items-center justify-center gap-2">
          <Button
            nativeButton={false}
            render={<Link href="/login" />}
            className="bg-gradient-to-r from-primary to-violet text-primary-foreground hover:opacity-90"
          >
            Log in
          </Button>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/register" />}
          >
            Sign up
          </Button>
        </div>
      </div>
    </div>
  )
}

export function ProfileView() {
  const { user, isLoading: authLoading, isWaking, updateUser } = useAuth()

  // --- Avatar ---
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [avatarBusy, setAvatarBusy] = useState(false)
  const [avatarError, setAvatarError] = useState<string | null>(null)

  async function handleAvatarPick(file: File | undefined) {
    if (!file) return
    setAvatarError(null)
    setAvatarBusy(true)

    try {
      const updated = await uploadAvatar(file)
      updateUser(updated)
    } catch (err) {
      setAvatarError(
        err instanceof Error ? err.message : 'Could not upload that photo.',
      )
    } finally {
      setAvatarBusy(false)
    }
  }

  async function handleAvatarRemove() {
    setAvatarError(null)
    setAvatarBusy(true)

    try {
      const updated = await removeAvatar()
      updateUser(updated)
    } catch (err) {
      setAvatarError(
        err instanceof Error ? err.message : 'Could not remove the photo.',
      )
    } finally {
      setAvatarBusy(false)
    }
  }

  // --- Profile info (email / ServiceNow username) ---
  const [name, setName] = useState(user?.name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [servicenowUsername, setServicenowUsername] = useState(
    user?.servicenowUsername ?? '',
  )
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSuccess, setProfileSuccess] = useState(false)
  const [profileSubmitting, setProfileSubmitting] = useState(false)

  async function handleProfileSubmit(e: FormEvent) {
    e.preventDefault()
    setProfileError(null)
    setProfileSuccess(false)
    setProfileSubmitting(true)

    try {
      const fields: {
        email?: string
        servicenowUsername?: string
        name?: string
      } = {}
      if (user && name !== user.name) fields.name = name
      if (user && email !== user.email) fields.email = email
      if (user && servicenowUsername !== user.servicenowUsername) {
        fields.servicenowUsername = servicenowUsername
      }

      if (Object.keys(fields).length === 0) {
        setProfileSubmitting(false)
        return
      }

      const updated = await updateProfile(fields)
      updateUser(updated)
      setProfileSuccess(true)
    } catch (err) {
      setProfileError(
        err instanceof Error ? err.message : 'Could not save those changes.',
      )
    } finally {
      setProfileSubmitting(false)
    }
  }

  // --- Password ---
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSuccess, setPasswordSuccess] = useState(false)
  const [passwordSubmitting, setPasswordSubmitting] = useState(false)

  async function handlePasswordSubmit(e: FormEvent) {
    e.preventDefault()
    setPasswordError(null)
    setPasswordSuccess(false)

    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match.')
      return
    }

    setPasswordSubmitting(true)

    try {
      await changePassword(currentPassword, newPassword)
      setPasswordSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setPasswordError(
        err instanceof Error ? err.message : 'Could not change your password.',
      )
    } finally {
      setPasswordSubmitting(false)
    }
  }

  if (authLoading) return isWaking ? <ServerWaking fullPage={false} /> : null
  if (!user) return <LoginRequired />

  return (
    <div className="relative isolate overflow-hidden px-4 py-10 sm:px-6">
      <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
        <div className="absolute left-1/2 top-[-200px] h-[480px] w-[720px] -translate-x-1/2 rounded-full bg-primary/[0.06] blur-[120px]" />
      </div>

      <div className="mx-auto max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Your profile
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your account and how you appear across the assistant.
          </p>
        </div>

        {/* Avatar */}
        <SectionCard
          title="Photo"
          description="Used across the assistant. Without a photo, your initials are shown instead."
        >
          <div className="mt-5 flex items-center gap-5">
            <UserAvatar user={user} size="lg" />
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  onChange={(e) => {
                    void handleAvatarPick(e.target.files?.[0])
                    e.target.value = ''
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  disabled={avatarBusy}
                  onClick={() => fileInputRef.current?.click()}
                  className="gap-1.5"
                >
                  <Upload className="size-4" />
                  {user.hasAvatar ? 'Replace photo' : 'Upload photo'}
                </Button>
                {user.hasAvatar && (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={avatarBusy}
                    onClick={() => void handleAvatarRemove()}
                    className="gap-1.5 text-red-400 hover:text-red-300"
                  >
                    <Trash2 className="size-4" />
                    Remove
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                PNG, JPEG, WebP or GIF, up to 10 MB.
              </p>
              {avatarError && (
                <p className="text-sm text-red-400">{avatarError}</p>
              )}
            </div>
          </div>
        </SectionCard>

        {/* Profile info */}
        <SectionCard
          title="Account details"
          description="Your display name is taken from your linked ServiceNow user."
        >
          <form onSubmit={handleProfileSubmit} className="mt-5 space-y-4">
            <AuthField
              id="name"
              label="Display name"
              icon={UserRound}
              type="text"
              autoComplete="name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />

            <AuthField
              id="email"
              label="Email"
              icon={Mail}
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />

            <AuthField
              id="servicenowUsername"
              label="ServiceNow username"
              icon={UserRound}
              type="text"
              autoComplete="off"
              required
              hint="Changing this re-verifies against your ServiceNow instance and updates your display name."
              value={servicenowUsername}
              onChange={(e) => setServicenowUsername(e.target.value)}
            />

            {profileError && (
              <p className="text-sm text-red-400">{profileError}</p>
            )}
            {profileSuccess && (
              <p className="text-sm text-primary">Saved.</p>
            )}

            <Button
              type="submit"
              disabled={profileSubmitting}
              className="h-10 bg-gradient-to-r from-primary to-violet text-primary-foreground hover:opacity-90"
            >
              {profileSubmitting ? 'Saving...' : 'Save changes'}
            </Button>
          </form>
        </SectionCard>

        {/* Password */}
        <SectionCard
          title="Password"
          description="Choose a new password for your account."
        >
          <form onSubmit={handlePasswordSubmit} className="mt-5 space-y-4">
            <AuthField
              id="currentPassword"
              label="Current password"
              icon={Lock}
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
            <AuthField
              id="newPassword"
              label="New password"
              icon={Lock}
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              hint="At least 8 characters."
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            <AuthField
              id="confirmPassword"
              label="Confirm new password"
              icon={Lock}
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />

            {passwordError && (
              <p className="text-sm text-red-400">{passwordError}</p>
            )}
            {passwordSuccess && (
              <p className="text-sm text-primary">Password updated.</p>
            )}

            <Button
              type="submit"
              disabled={passwordSubmitting}
              className="h-10 bg-gradient-to-r from-primary to-violet text-primary-foreground hover:opacity-90"
            >
              {passwordSubmitting ? 'Updating...' : 'Update password'}
            </Button>
          </form>
        </SectionCard>
      </div>
    </div>
  )
}