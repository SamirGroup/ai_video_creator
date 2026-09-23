import { useTranslation } from 'react-i18next'

import { LanguageSwitcher } from './LanguageSwitcher'
import { ThemeToggle } from './ThemeToggle'
import { UserMenu } from './UserMenu'
import { useUiStore } from '@/stores/uiStore'

export function Topbar() {
  const { t } = useTranslation()
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-surface/80 px-4 backdrop-blur">
      <button
        type="button"
        onClick={toggleSidebar}
        aria-label={t('nav.toggle')}
        className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5" aria-hidden="true">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <div className="hidden lg:block" />
      <div className="flex items-center gap-2">
        <LanguageSwitcher />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  )
}
