'use client'

import { useState } from 'react'
import type { FormEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Lock, Mail } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { AuthCard, AuthField, AuthShell } from '@/components/auth-shell'

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      await login(email, password)
      router.push('/incident')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Login failed. Please try again.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell imageSrc="/auth_hero.jpg" imageSide="left">
      <AuthCard
        title="Welcome back"
        subtitle="Log in to use the Incident Assistant and create ServiceNow incidents under your account."
        footer={
          <>
            Don&apos;t have an account?{' '}
            <Link href="/register" className="font-medium text-primary hover:underline">
              Create one
            </Link>
          </>
        }
      >
        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <AuthField
            id="email"
            label="Email"
            icon={Mail}
            type="email"
            autoComplete="email"
            required
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <AuthField
            id="password"
            label="Password"
            icon={Lock}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {error && <p className="text-sm text-red-400">{error}</p>}

          <Button
            type="submit"
            disabled={isSubmitting}
            className="h-11 w-full bg-gradient-to-r from-primary to-violet text-primary-foreground hover:opacity-90"
          >
            {isSubmitting ? 'Logging in...' : 'Log in'}
          </Button>
        </form>
      </AuthCard>
    </AuthShell>
  )
}