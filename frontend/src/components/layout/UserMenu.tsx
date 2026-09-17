import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/cn'

export function UserMenu() {
  const { t } = useTranslation()
  const { user, logout, isLoggingOut } = useAuth()
  const [isOpen, setIsOpen] = useState(false)

  const initials = (user?.full_name ?? user?.email ?? '?')
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-600 text-xs font-semibold text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        {initials}
      </button>
      {isOpen && (
        <>
          {/* Click-outside overlay */}
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setIsOpen(false)}
          />
          <div
            role="menu"
            className={cn(
              'absolute right-0 z-20 mt-2 w-56 animate-slide-up rounded-md border border-border bg-surface p-1 shadow-lg',
            )}
          >
            <div className="border-b border-border px-3 py-2">
              <p className="truncate text-sm font-medium text-foreground">
                {user?.full_name}
              </p>
              <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
            </div>
            <button
              type="button"
              role="menuitem"
              disabled={isLoggingOut}
              onClick={() => logout()}
              className="mt-1 flex w-full items-center rounded px-3 py-2 text-start text-sm text-destructive-600 hover:bg-destructive-50 disabled:opacity-60 dark:hover:bg-destructive-700/10"
            >
              {isLoggingOut ? t('common.loading') : t('nav.logout')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
