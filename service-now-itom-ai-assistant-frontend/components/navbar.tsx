'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { Menu as MenuPrimitive } from '@base-ui/react/menu'
import {
  LogOut,
  Menu as MenuIcon,
  Moon,
  Sun,
  UserCog,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SiteLogo } from '@/components/site-logo'
import { UserAvatar } from '@/components/user-avatar'
import { useAuth } from '@/lib/auth-context'
import { useTheme } from '@/lib/theme-context'
import { cn } from '@/lib/utils'

const links = [
  { href: '/', label: 'Home' },
  { href: '/documentation', label: 'Documentation Assistant' },
  { href: '/incident', label: 'Incident Assistant' },
]

const menuPopupClass =
  'z-50 min-w-64 origin-[var(--transform-origin)] rounded-xl border border-border/70 bg-card p-1 shadow-xl shadow-black/20 outline-none data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0 data-[open]:scale-100 data-[open]:opacity-100'

const menuItemClass =
  'flex cursor-pointer select-none items-center gap-2 rounded-lg px-3 py-2 text-sm text-foreground outline-none data-[highlighted]:bg-secondary'

/** Sun/Moon pill, matching the same shape everywhere it appears (the
 * account dropdown here, and the mobile menu below). */
function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()

  return (
    <div
      className={cn(
        'flex items-center gap-0.5 rounded-full bg-secondary/70 p-1',
        className,
      )}
      role="radiogroup"
      aria-label="Theme"
    >
      <button
        type="button"
        role="radio"
        aria-checked={theme === 'dark'}
        aria-label="Dark theme"
        onClick={() => setTheme('dark')}
        className={cn(
          'flex size-6 items-center justify-center rounded-full transition-colors',
          theme === 'dark'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        <Moon className="size-3.5" />
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={theme === 'light'}
        aria-label="Light theme"
        onClick={() => setTheme('light')}
        className={cn(
          'flex size-6 items-center justify-center rounded-full transition-colors',
          theme === 'light'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        <Sun className="size-3.5" />
      </button>
    </div>
  )
}

export function Navbar() {
  const pathname = usePathname()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const { user, isLoading, logout } = useAuth()

  async function handleLogout() {
    await logout()
    router.push('/')
  }

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/70 backdrop-blur-xl">
      <nav
        className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6"
        aria-label="Main navigation"
      >
        <SiteLogo />

        {/* Desktop links */}
        <div className="hidden items-center gap-1 md:flex">
          {links.map((link) => {
            const active =
              link.href === '/'
                ? pathname === '/'
                : pathname.startsWith(link.href)
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  active
                    ? 'bg-secondary text-foreground'
                    : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
                )}
              >
                {link.label}
              </Link>
            )
          })}
        </div>

        <div className="hidden items-center gap-2 md:flex">
          {/* Account */}
          {!isLoading && user && (
            <MenuPrimitive.Root>
              <MenuPrimitive.Trigger
                render={
                  <button
                    aria-label="Account menu"
                    className="rounded-full outline-none transition-opacity hover:opacity-85"
                  />
                }
              >
                <UserAvatar size="md" />
              </MenuPrimitive.Trigger>
              <MenuPrimitive.Portal>
                <MenuPrimitive.Positioner sideOffset={8} align="end">
                  <MenuPrimitive.Popup className={menuPopupClass}>
                    <div className="flex items-center gap-3 px-3 py-2.5">
                      <UserAvatar size="md" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">
                          {user.name || user.email}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {user.email}
                        </p>
                        {user.servicenowUsername && (
                          <p className="truncate text-xs text-muted-foreground">
                            ServiceNow: {user.servicenowUsername}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="my-1 h-px bg-border/70" />

                    <MenuPrimitive.Item
                      render={<Link href="/profile" />}
                      className={menuItemClass}
                    >
                      <UserCog className="size-4 text-muted-foreground" aria-hidden="true" />
                      Profile
                    </MenuPrimitive.Item>

                    <div className="flex items-center justify-between px-3 py-2">
                      <span className="text-sm text-foreground">Theme</span>
                      <ThemeToggle />
                    </div>

                    <div className="my-1 h-px bg-border/70" />

                    <MenuPrimitive.Item
                      onClick={handleLogout}
                      className={menuItemClass}
                    >
                      <LogOut className="size-4 text-muted-foreground" aria-hidden="true" />
                      Log out
                    </MenuPrimitive.Item>
                  </MenuPrimitive.Popup>
                </MenuPrimitive.Positioner>
              </MenuPrimitive.Portal>
            </MenuPrimitive.Root>
          )}

          {!isLoading && !user && (
            <div className="flex items-center gap-1">
              <ThemeToggle className="mr-1" />
              <Link
                href="/login"
                className="rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
              >
                Log in
              </Link>
              <Button
                nativeButton={false}
                variant="outline"
                render={<Link href="/register" />}
                className="h-9 px-4"
              >
                Sign up
              </Button>
            </div>
          )}
        </div>

        {/* Mobile toggle */}
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="size-5" /> : <MenuIcon className="size-5" />}
        </Button>
      </nav>

      {/* Mobile menu */}
      {open && (
        <div className="border-t border-border/60 bg-background/95 px-4 py-3 md:hidden">
          <div className="flex flex-col gap-1">
            {links.map((link) => {
              const active =
                link.href === '/'
                  ? pathname === '/'
                  : pathname.startsWith(link.href)
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setOpen(false)}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                    active
                      ? 'bg-secondary text-foreground'
                      : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
                  )}
                >
                  {link.label}
                </Link>
              )
            })}

            <div className="my-2 h-px bg-border/70" />

            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-sm font-medium text-foreground">Theme</span>
              <ThemeToggle />
            </div>

            {!isLoading && user ? (
              <>
                <div className="my-1 h-px bg-border/70" />
                <div className="flex items-center gap-3 px-3 py-2">
                  <UserAvatar size="sm" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">
                      {user.name || user.email}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {user.email}
                    </p>
                  </div>
                </div>
                <Link
                  href="/profile"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                >
                  <UserCog className="size-4" aria-hidden="true" />
                  Profile
                </Link>
                <button
                  onClick={() => {
                    setOpen(false)
                    void handleLogout()
                  }}
                  className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                >
                  <LogOut className="size-4" aria-hidden="true" />
                  Log out
                </button>
              </>
            ) : (
              !isLoading && (
                <>
                  <div className="my-1 h-px bg-border/70" />
                  <Link
                    href="/login"
                    onClick={() => setOpen(false)}
                    className="rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                  >
                    Log in
                  </Link>
                  <Link
                    href="/register"
                    onClick={() => setOpen(false)}
                    className="rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                  >
                    Sign up
                  </Link>
                </>
              )
            )}
          </div>
        </div>
      )}
    </header>
  )
}