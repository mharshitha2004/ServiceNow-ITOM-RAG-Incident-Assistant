'use client'

import { useState } from 'react'
import type { FormEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { IdCard, Lock, Mail, UserRound } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { AuthCard, AuthField, AuthShell } from '@/components/auth-shell'

export default function RegisterPage() {
  const router = useRouter()
  const { register } = useAuth()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [servicenowUsername, setServicenowUsername] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      await register(email, password, servicenowUsername, name)
      router.push('/incident')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Registration failed. Please try again.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell imageSrc="/auth_login.png" imageSide="right">
      <AuthCard
        title="Create an account"
        subtitle="Link your ServiceNow username so incidents you create show you as the caller."
        footer={
          <>
            Already have an account?{' '}
            <Link href="/login" className="font-medium text-primary hover:underline">
              Log in
            </Link>
          </>
        }
      >
        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <AuthField
            id="name"
            label="Full name"
            icon={IdCard}
            type="text"
            autoComplete="name"
            required
            placeholder="e.g. Mandadi Harshitha Reddy"
            hint="How you'll appear across the assistant."
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
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <AuthField
            id="password"
            label="Password"
            icon={Lock}
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            hint="At least 8 characters."
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <AuthField
            id="servicenowUsername"
            label="ServiceNow username"
            icon={UserRound}
            type="text"
            autoComplete="off"
            required
            placeholder="e.g. abel.tuter"
            hint="Must match an existing user on your ServiceNow instance - we verify it when you submit."
            value={servicenowUsername}
            onChange={(e) => setServicenowUsername(e.target.value)}
          />

          {error && <p className="text-sm text-red-400">{error}</p>}

          <Button
            type="submit"
            disabled={isSubmitting}
            className="h-11 w-full bg-gradient-to-r from-primary to-violet text-primary-foreground hover:opacity-90"
          >
            {isSubmitting ? 'Creating account...' : 'Create account'}
          </Button>
        </form>
      </AuthCard>
    </AuthShell>
  )
}