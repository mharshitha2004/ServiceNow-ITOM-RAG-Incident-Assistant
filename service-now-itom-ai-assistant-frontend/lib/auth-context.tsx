'use client'

import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { usePathname } from 'next/navigation'
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  type User,
} from '@/lib/auth'
import { ServerWakingToast } from '@/components/server-waking'

type AuthContextValue = {
  user: User | null
  // True only while the initial session check (on page load) is
  // in flight - lets pages avoid a login-required flash before we
  // know whether a session cookie is actually valid.
  isLoading: boolean
  /** True when that initial check has been running for a few seconds -
   * i.e. the free-tier backend is asleep and booting. Pages use it to
   * show "Waking up the server…" instead of a blank screen. */
  isWaking: boolean
  login: (email: string, password: string) => Promise<void>
  register: (
    email: string,
    password: string,
    servicenowUsername: string,
    name: string,
  ) => Promise<void>
  logout: () => Promise<void>
  /** Pushes a fresh user object into context - call this after any
   * profile/password/avatar change so the navbar etc. update immediately
   * without a full page reload. */
  updateUser: (user: User) => void
  /** Bumped every time updateUser() is called. The avatar photo is served
   * from a fixed URL, so components append this as a query param to force
   * the browser to refetch it after an upload/removal instead of showing
   * a stale cached image. */
  avatarVersion: number
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isWaking, setIsWaking] = useState(false)
  const pathname = usePathname()
  const [avatarVersion, setAvatarVersion] = useState(0)

  useEffect(() => {
    // A warm backend answers /auth/me in well under a second. If it's
    // still pending after 2.5s, the server is almost certainly cold-starting.
    const wakingTimer = setTimeout(() => setIsWaking(true), 2500)

    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => {
        clearTimeout(wakingTimer)
        setIsWaking(false)
        setIsLoading(false)
      })

    return () => clearTimeout(wakingTimer)
  }, [])

  async function login(email: string, password: string) {
    const loggedInUser = await loginRequest(email, password)
    setUser(loggedInUser)
  }

  async function register(
    email: string,
    password: string,
    servicenowUsername: string,
    name: string,
  ) {
    const registeredUser = await registerRequest(
      email,
      password,
      servicenowUsername,
      name,
    )
    setUser(registeredUser)
  }

  async function logout() {
    await logoutRequest()
    setUser(null)
  }

  function updateUser(next: User) {
    setUser(next)
    setAvatarVersion((v) => v + 1)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isWaking,
        login,
        register,
        logout,
        updateUser,
        avatarVersion,
      }}
    >
      {children}
      {/* The incident and profile pages show a full "waking up" card
          themselves; everywhere else gets this small notice. */}
      {isWaking &&
        !pathname?.startsWith('/incident') &&
        !pathname?.startsWith('/profile') && <ServerWakingToast />}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }

  return context
}